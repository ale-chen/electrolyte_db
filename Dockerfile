FROM python:3.11.4-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /app
ADD . /app
COPY ./requirements.txt /electro_app/requirements.txt

RUN pip install --no-cache-dir --upgrade -r /electro_app/requirements.txt
RUN pwd

COPY static /app/static
#COPY templates /app/templates

EXPOSE 80

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "80"]