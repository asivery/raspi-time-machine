#!/bin/bash

echo "Installing UDEV rules for NetworkManager..."
cp -v ./00-nm-kill-eth0.rules /etc/udev/rules.d/

echo "Installing binary dependencies..."
apt update
apt upgrade -y
apt install python3 python3-pip network-manager libcairo2-dev libgirepository1.0-dev libdbus-1-dev -y

echo "Installing python dependencies..."
python3 -m pip install -r ../raspi-configurator/requirements.txt

echo "Installing raspi-configurator..."
cp -rv ../raspi-configurator /opt/

echo "Updating permissions..."
for e in main.py modules/time_machine/prepare.sh
do
    chmod a+x "/opt/raspi-configurator/$e"
done

echo "Writing config files..."
cp ./configurator.service /etc/systemd/system/
mkdir /etc/configurator

echo "Configuring services..."
systemctl enable configurator
systemctl enable NetworkManager
systemctl enable systemd-resolved
systemctl disable dhcpcd
systemctl stop dhcpcd
systemctl restart NetworkManager
systemctl start systemd-resolved
