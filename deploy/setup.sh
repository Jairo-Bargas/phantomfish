#!/usr/bin/env bash
# Se corre UNA vez en el servidor Ubuntu recién creado.
#   bash ~/phantomfish/deploy/setup.sh
set -euo pipefail

echo ">> Instalando Docker..."
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker "$USER"
fi

echo ">> Abriendo los puertos 80 y 443 en el firewall del servidor..."
sudo iptables -I INPUT 1 -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 1 -p tcp --dport 443 -j ACCEPT

if ! command -v netfilter-persistent >/dev/null 2>&1; then
  sudo DEBIAN_FRONTEND=noninteractive apt-get update -y
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y iptables-persistent
fi
sudo netfilter-persistent save

echo
echo "======================================================================"
echo " Docker instalado y firewall abierto."
echo
echo " 1) Cerrá esta sesión SSH y volvé a entrar (para usar Docker sin sudo)."
echo " 2) Acordate de abrir 80 y 443 tambien en la 'Security List' de Oracle"
echo "    (eso se hace en la web de Oracle, ver la guía)."
echo " 3) Después:"
echo "      cd ~/phantomfish/deploy"
echo "      cp .env.example .env"
echo "      nano .env          # completar SITE_ADDRESS y SEED_PASSWORD"
echo "      docker compose up -d --build"
echo "======================================================================"
