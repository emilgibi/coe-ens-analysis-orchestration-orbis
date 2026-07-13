# app/celery_app.py

from celery import Celery

BROKER_URL = "amqp://cyvhztoo:BzEGwP10ORBC-w-uTLeyDzN74eohgd58@ostrich.lmq.cloudamqp.com/cyvhztoo"

celery_app = Celery("ens_tasks", broker=BROKER_URL, backend="rpc://")


@celery_app.task(name="hello")
def hello():
    print("🎉 Hello task called!")
import app.core.utils.celery_worker
