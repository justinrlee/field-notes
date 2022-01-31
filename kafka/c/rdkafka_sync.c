#include<stdio.h>
#include<string.h>
#include<pthread.h>
#include<stdlib.h>

#include <librdkafka/rdkafka.h>

const char charset[] = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789,.-#'?!";   

char errstr[512];      /* librdkafka API error reporting buffer */

const int MAX_THREADS = 32;
const int MSGS = 32000;
const int PAYLOAD_SIZE = 1024;

const int UNACKED = -123;

int MSGS_PER_THREAD = MSGS / MAX_THREADS;

// Thread arg
typedef struct _kafka_t {
  rd_kafka_t *rk;
  rd_kafka_conf_t *rk_conf;

  rd_kafka_topic_t *rkt;
} kafka_t;

static void sync_msg_cb(rd_kafka_t *rk, const rd_kafka_message_t *rkmessage, void *opaque) {
	if (rkmessage->_private) {
		rd_kafka_resp_err_t *errp = (rd_kafka_resp_err_t *)rkmessage->_private;
		*errp = rkmessage->err;
	}
}

// Initialize: create rd_kafka and rd_kafka_topic for use by processor
static void initialize_rk(kafka_t *k) {

  // Not currently exposed
  rd_kafka_topic_conf_t *rkt_conf;
  rkt_conf = rd_kafka_conf_get_default_topic_conf(k->rk_conf);

  // Set the synchronous callback
  rd_kafka_conf_set_dr_msg_cb(k->rk_conf, sync_msg_cb);

  k->rk = rd_kafka_new(RD_KAFKA_PRODUCER, k->rk_conf, errstr, sizeof(errstr));

  k->rkt = rd_kafka_topic_new(k->rk, "test", rkt_conf);
}

static void* processor(void *args) {
  kafka_t *k = (kafka_t *) args;
  rd_kafka_resp_err_t err;

  printf("\nStarting thread %lu\n", pthread_self());
  
  // Right now we generate a dummy load for each thread, inside the processor thread
  srand(0);
  int *p_m = malloc(sizeof(int));
  char *payload = (char *) malloc(PAYLOAD_SIZE * sizeof(char));

  int key;
  for (int n = 0; n < PAYLOAD_SIZE; n++) {
    key = rand() % (int)(sizeof charset -1);
    payload[n] = charset[key];
  }

  for (int i; i < MSGS_PER_THREAD; i++) {
    
    *p_m = UNACKED;

    // printf("producing message to rd_kafka");
    err = rd_kafka_produce( k->rkt,
                      RD_KAFKA_PARTITION_UA,
                      0,
                      payload, PAYLOAD_SIZE,
                      NULL, 0,
                      p_m
                      );

    // printf("message sent to rd_kafka");
    // No error handling yet
    if (err) printf("Unable to produce message\n");

    // This makes it synchronous; wait for the callback to get called (identified by the fact that p_m is no longer -123);
    // while (*p_m == UNACKED) rd_kafka_poll(k->rk, 0);
    // printf("ack received");

  }
  printf("\nFinishing thread\n");
  free(payload);
  free(p_m);
}

int main(void)
{
  kafka_t *k = malloc(sizeof(kafka_t));
  int err; // Used for error handling
  srand(0);
  int i = 0;

  pthread_t threads[MAX_THREADS];
  
  // Todo populate with params; for now use defaults
  k->rk_conf = rd_kafka_conf_new();
  rd_kafka_conf_set(k->rk_conf, "bootstrap.servers", "localhost:9092", errstr, sizeof(errstr));
  rd_kafka_conf_set(k->rk_conf, "linger.ms", "0.1", errstr, sizeof(errstr));

  initialize_rk(k);

  while (i < MAX_THREADS) {
    printf("Creating thread\n");

    err = pthread_create(&(threads[i]), NULL, &processor, k);
    if (err != 0)
        printf("\ncan't create thread :[%s]", strerror(err));
    else
        printf("\n Thread created successfully\n");
    i++;
  }
  printf("All threads started\n");

  for(int t = 0; t < MAX_THREADS; t++) {
    pthread_join(threads[t], NULL);
    printf("Thread completed\n");
  }

  rd_kafka_flush(k->rk, 30000);
  free(k);

  printf("Exiting\n");


  return 0;
}