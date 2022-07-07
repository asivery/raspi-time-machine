#!/bin/bash

set -x

iptables -t nat -F
iptables -F

sysctl -w net.ipv4.ip_forward=1
ifconfig eth0 192.168.2.1 netmask 255.255.255.0

PROXY_FULL_IP=$(ip -f inet addr show wlan0 | sed -En -e 's/.*inet ([0-9/.]+).*/\1/p')
PROXY_IP=${PROXY_FULL_IP%/*}
LAN_IP=${PROXY_IP%.*}.0
LAN_NET=$LAN_IP/${PROXY_FULL_IP##*/}
PROXY_PORT=8888

iptables -t nat -A PREROUTING -i eth0 -s $LAN_NET -d $LAN_NET -p tcp --dport 80 -j ACCEPT
iptables -t nat -A PREROUTING -i eth0 -p tcp --dport 80 -j DNAT --to $PROXY_IP:$PROXY_PORT
iptables -t nat -I POSTROUTING -o wlan0 -s $LAN_NET -d $PROXY_IP -p tcp -j SNAT --to $LAN_IP
iptables -t nat -A POSTROUTING --out-interface wlan0 -j MASQUERADE
iptables -I FORWARD -i eth0 --out-interface wlan0 -s $LAN_NET -d $PROXY_IP -p tcp --dport $PROXY_PORT -j ACCEPT
