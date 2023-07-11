FROM python:3.11.4-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /app
ADD . /app
COPY ./requirements.txt /electro_app/requirements.txt

RUN apt-get update && apt-get install -y git
RUN pip install --no-cache-dir --upgrade -r /electro_app/requirements.txt

ARG SSH_PRIVATE_KEY
RUN mkdir -p /root/.ssh
RUN echo "${SSH_PRIVATE_KEY}" > /root/.ssh/id_ed25519
RUN chmod 600 /root/.ssh/id_ed25519
RUN touch /root/.ssh/known_hosts
RUN ssh-keyscan github.com >> /root/.ssh/known_hosts

RUN mkdir my_project
WORKDIR /app/my_project
RUN git clone git@github.com:ale-chen/electrolyte_db.git .

#COPY static /app/static
WORKDIR /app/my_project/app
#COPY templates /app/templates

EXPOSE 8000

RUN chmod +x start.sh

CMD ["./start.sh"]