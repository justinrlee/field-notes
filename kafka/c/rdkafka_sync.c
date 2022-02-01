#include<stdio.h>
#include<string.h>
#include<pthread.h>
#include<stdlib.h>
#include<getopt.h>

#include <librdkafka/rdkafka.h>

const char charset[] = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789,.-#'?!";   

char errstr[512];      /* librdkafka API error reporting buffer */

const int UNACKED = -123;

// Params passed to thread: information about rdkafka instance, as well as number of messages (and message size)
typedef struct _kafka_t {
  rd_kafka_t *rk;
  rd_kafka_conf_t *rk_conf;

  rd_kafka_topic_t *rkt;

  int messages;
  int message_size;
  int verbosity;
} processor_config_t;

// Synchronous callback - modify the object referenced by the pointer
static void sync_msg_cb(rd_kafka_t *rk, const rd_kafka_message_t *rkmessage, void *opaque) {
	if (rkmessage->_private) {
		rd_kafka_resp_err_t *errp = (rd_kafka_resp_err_t *)rkmessage->_private;
		*errp = rkmessage->err;
	}
}

// Initialize: create rd_kafka and rd_kafka_topic for use by processor
static void initialize_rk(processor_config_t *k, char *topic_name) {

  // Not currently exposed
  rd_kafka_topic_conf_t *rkt_conf;
  rkt_conf = rd_kafka_conf_get_default_topic_conf(k->rk_conf);

  rd_kafka_conf_set_dr_msg_cb(k->rk_conf, sync_msg_cb);

  k->rk = rd_kafka_new(RD_KAFKA_PRODUCER, k->rk_conf, errstr, sizeof(errstr));
  k->rkt = rd_kafka_topic_new(k->rk, topic_name, rkt_conf);
}

static void* processor(void *args) {
  processor_config_t *k = (processor_config_t *) args;
  rd_kafka_resp_err_t err;

  if (k->verbosity > 0)
    printf("Starting thread %lu\n", pthread_self());
  
  // Right now we generate a dummy load for each thread, inside the processor thread; for better benchmarking could move to initialize and add timestamps
  int *p_m = malloc(sizeof(int));
  char *payload = (char *) malloc(k->message_size * sizeof(char));

  int n, i, key;
  for (n = 0; n < k->message_size; n++) {
    key = rand() % (int)(sizeof charset -1);
    payload[n] = charset[key];
  }

  for (i; i < k->messages; i++) {
    *p_m = UNACKED;

    if (k->verbosity > 2)
      printf("T %lu:%i producing message\n", pthread_self(), i);
    else if (k->verbosity > 1)
      printf("p");
      
    err = rd_kafka_produce( k->rkt,
                      RD_KAFKA_PARTITION_UA,
                      0,
                      payload, k->message_size,
                      NULL, 0,
                      p_m
                      );

    if (k->verbosity > 2)
      printf("T %lu:%i queued message\n", pthread_self(), i);
    else if (k->verbosity > 1)
      printf("q");

    // No error handling yet
    if (err) printf("Unable to produce message\n");

    // This makes it synchronous; wait for the callback to get called (identified by the fact that p_m is no longer -123);
    while (*p_m == UNACKED) rd_kafka_poll(k->rk, 0);
    
    if (k->verbosity > 2)
      printf("T %lu:%i ack received\n", pthread_self(), i);
    else if (k->verbosity > 1)
      printf("a");

  }

  if (k->verbosity > 0)
    printf("Thread %lu finished\n", pthread_self());
  free(payload);
  free(p_m);
}

int main(int argc, char **argv)
{
  int err; // Used for error handling
  processor_config_t *k = malloc(sizeof(processor_config_t));
  srand(0);
  int i = 0;
  int opt;

  int max_threads = 4;
  int total_messages = 16000;
  // float linger_ms = "0.1";
  char *linger_ms = "0.1";
  char *bootstrap_servers = "localhost:9092";
  char *acks = "1";
  char *topic_name = "test";
  
  k->message_size = 1024;
  k->verbosity = 0;

  // Currently no type checking / error handling
  while ((opt = getopt(argc, argv, "T:M:S:b:t:l:a:v:")) != -1) {
    switch (opt) {
      case 'a':
        acks = optarg;
        break;
      case 't':
        topic_name = optarg;
        break;
      case 'b':
        bootstrap_servers = optarg;
        break;
      case 'l':
        linger_ms = optarg;
        break;
      case 'M':
        total_messages = atoi(optarg);
        break;
      case 'T':
        max_threads = atoi(optarg); 
        break;
      case 'S':
        k->message_size = atoi(optarg);
        break;
      case 'v':
        k->verbosity = atoi(optarg);
        break;
      default:
        fprintf(stderr, "Unknown option: %c\n", opt);
        exit(1);
    }
  }

  // If messages/threads is not an integer, reduce messages so that it is.
  k->messages = total_messages / max_threads;
  total_messages = k->messages * max_threads;

  fprintf(stdout, "Writing %i %i-byte messages using %i threads (%i per thread)\n",
            total_messages,
            k->message_size,
            max_threads,
            k->messages);
  fprintf(stdout, "Topic %s for bootstrap server %s\n",
            topic_name,
            bootstrap_servers);
  fprintf(stdout, "linger.ms = %s\n", linger_ms);
  fprintf(stdout, "acks = %s\n", acks);

  pthread_t threads[max_threads];
  
  // Todo populate with params; for now use defaults
  k->rk_conf = rd_kafka_conf_new();
  rd_kafka_conf_set(k->rk_conf, "bootstrap.servers", bootstrap_servers, errstr, sizeof(errstr));
  rd_kafka_conf_set(k->rk_conf, "linger.ms", linger_ms, errstr, sizeof(errstr));
  rd_kafka_conf_set(k->rk_conf, "acks", acks, errstr, sizeof(errstr));

  initialize_rk(k, topic_name);

  while (i < max_threads) {
    if (k->verbosity > 0)
      printf("Creating thread\n");

    err = pthread_create(&(threads[i]), NULL, &processor, k);
    if (err != 0)
      printf("\ncan't create thread :[%s]", strerror(err));
    else if (k->verbosity > 0)
      printf("Thread created successfully\n");
    i++;
  }
  printf("All threads started\n");

  for(int t = 0; t < max_threads; t++) {
    pthread_join(threads[t], NULL);
    if (k->verbosity > 0)
      printf("Thread joined\n");
  }

  rd_kafka_flush(k->rk, 30000);
  free(k);

  printf("All threads completed\n");


  return 0;
}