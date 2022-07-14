package io.justinrlee.mqtt;


import org.eclipse.paho.client.mqttv3.*;
import org.eclipse.paho.client.mqttv3.MqttException;
import org.eclipse.paho.client.mqttv3.persist.MemoryPersistence;

import io.justinrlee.mqtt.protobuf.Person;

import java.util.Arrays;
import java.util.UUID;
import java.util.Random;

import static java.nio.charset.StandardCharsets.UTF_8;


/**
 * Produces protobuf-encoded messages to the local MQTT listener
 *
 */
public class MqttProtobufProducer 
{
    public static void main( String[] args )
    {
        System.out.println( "Starting Producer!" );

        // String topic        = "MQTT Examples";
        int qos             = 2;
        String broker       = "tcp://localhost:1883";
        String clientId     = "JavaSample";
        MemoryPersistence persistence = new MemoryPersistence();

        Person person;
        String strUUID;
        MqttClient mqttClient = null;
        Random r = new Random();

        Thread exitThread;


        try {
            mqttClient = new MqttClient(broker, clientId, persistence);
            MqttConnectOptions connOpts = new MqttConnectOptions();
            connOpts.setCleanSession(true);
            System.out.println("Connecting to broker: " + broker);
            mqttClient.connect(connOpts);
            System.out.println("Connected");

            // Runtime.getRuntime().addShutdownHook(new Thread()
            // {
            //     public void run()
            //     {
            //         try {
            //             mqttClient.disconnect();
            //         } catch (Exception e) {
            //             System.out.println("Unable to disconnect");
            //         }
            //         System.out.println("Exiting");
            //     }
            // });

        } catch(MqttException me) {
            System.out.println("reason " + me.getReasonCode());
            System.out.println("msg " + me.getMessage());
            System.out.println("loc " + me.getLocalizedMessage());
            System.out.println("cause " + me.getCause());
            System.out.println("excep " + me);
            me.printStackTrace();
        }

        for (;;) 
        {
            // 123e4567-e89b-12d3-a456-426614174000
            // 012345678901234567890123456789012345
            strUUID = UUID.randomUUID().toString();

            person = Person.newBuilder()
                .setId(r.nextInt(10000))
                .setName(strUUID.substring(0,8))
                .setEmail(strUUID.substring(9,13) + "@" + strUUID.substring(14,18) + ".local")
                .addPhones(
                Person.PhoneNumber.newBuilder()
                    .setNumber(strUUID.substring(24))
                    .setType(Person.PhoneType.HOME))
                .build();

            try {
                System.out.println("Publishing message: " + person.toByteArray());
                // System.out.println("Publishing message: "+content);
                MqttMessage message = new MqttMessage(person.toByteArray());
                // MqttMessage message = new MqttMessage(content.getBytes());
                message.setQos(qos);
                mqttClient.publish(strUUID.substring(19,23), message);
                System.out.println("Message published");
                // mqttClient.disconnect();
                // System.out.println("Disconnected");
                // System.exit(0);
            } catch(MqttException me) {
                System.out.println("reason " + me.getReasonCode());
                System.out.println("msg " + me.getMessage());
                System.out.println("loc " + me.getLocalizedMessage());
                System.out.println("cause " + me.getCause());
                System.out.println("excep " + me);
                me.printStackTrace();
            }
        }
    }
}
