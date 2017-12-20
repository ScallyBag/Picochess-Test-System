#!/usr/bin/env python
import pika

# connection = pika.BlockingConnection(pika.ConnectionParameters(host='localhost'))
connection = pika.BlockingConnection(pika.ConnectionParameters(host='178.63.72.77'))
channel = connection.channel()

exchange = '60005'  # Al's RevII
channel.exchange_declare(exchange=exchange, exchange_type='fanout')

result = channel.queue_declare(exclusive=True)
queue_name = result.method.queue

channel.queue_bind(exchange=exchange, queue=queue_name)

print(' [*] Waiting for messages. To exit press CTRL+C')


def callback(ch, method, properties, body):
    print(" [x] %r" % body)


channel.basic_consume(callback, queue=queue_name, no_ack=True)
channel.start_consuming()
