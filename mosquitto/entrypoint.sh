#!/bin/sh
set -eu
cp /run/secrets/mqtt-passwords.txt /tmp/passwords
mosquitto_passwd -U /tmp/passwords
chown mosquitto:mosquitto /tmp/passwords
chmod 600 /tmp/passwords
chown -R mosquitto:mosquitto /mosquitto/data
exec mosquitto -c /mosquitto/config/mosquitto.conf
