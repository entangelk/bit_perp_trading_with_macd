#!/bin/bash

domains=(entangelk.o-r.kr)
email="dyrkd12@naver.com" # 실제 이메일 주소로 변경하세요

data_path="./certbot"
rsa_key_size=4096
staging=0 # 테스트 시 1로 설정, 실제 인증서 발급 시 0으로 설정

if [ -d "$data_path" ]; then
  read -p "Existing data found. Continue and replace existing certificates? (y/N) " decision
  if [ "$decision" != "Y" ] && [ "$decision" != "y" ]; then
    exit
  fi
fi

mkdir -p "$data_path/conf/live/$domains"
mkdir -p "$data_path/www"

echo "### Creating dummy certificate for $domains ..."
openssl req -x509 -nodes -newkey rsa:$rsa_key_size -days 1\
  -keyout "$data_path/conf/live/$domains/privkey.pem" \
  -out "$data_path/conf/live/$domains/fullchain.pem" \
  -subj "/CN=localhost"

echo "### Starting nginx ..."
docker-compose up --force-recreate -d nginx

echo "### Deleting dummy certificate for $domains ..."
docker-compose run --rm --entrypoint "\
  rm -Rf /etc/letsencrypt/live/$domains && \
  rm -Rf /etc/letsencrypt/archive/$domains && \
  rm -Rf /etc/letsencrypt/renewal/$domains.conf" certbot

echo "### Requesting Let's Encrypt certificate for $domains ..."
docker-compose run --rm --entrypoint "\
  certbot certonly --webroot -w /var/www/certbot \
    --email $email \
    -d $domains \
    --rsa-key-size $rsa_key_size \
    --agree-tos \
    --force-renewal" certbot

echo "### Reloading nginx ..."
docker-compose exec nginx nginx -s reload