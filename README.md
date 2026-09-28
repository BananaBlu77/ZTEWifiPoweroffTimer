# ZTEWifiPoweroffTimer

Script per Raspberry Pi 4 che disattiva il Wi-Fi di un router ZTE (es. H3600) a mezzanotte e lo riattiva alle 07:00 tramite la console web (`192.168.1.1`).

## 1) Installazione

```bash
cd /home/pi/ZTEWifiPoweroffTimer
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
chmod +x zte_wifi_control.py install_cron.sh
```

## 2) Test manuale comandi

```bash
# Spegne il Wi-Fi
ZTE_HOST=192.168.1.1 ZTE_USERNAME=admin ZTE_PASSWORD='digi' ./zte_wifi_control.py off

# Riaccende il Wi-Fi
ZTE_HOST=192.168.1.1 ZTE_USERNAME=admin ZTE_PASSWORD='digi' ./zte_wifi_control.py on
```

## 3) Configurazione automatica giornaliera

Crea un file environment (per non salvare password nel crontab):

```bash
mkdir -p ~/.config
cat > ~/.config/zte-wifi-timer.env <<'EOF'
export ZTE_HOST=192.168.1.1
export ZTE_USERNAME=admin
export ZTE_PASSWORD='digi'
EOF
chmod 600 ~/.config/zte-wifi-timer.env
```

Poi installa il cron:

```bash
./install_cron.sh /home/pi/ZTEWifiPoweroffTimer/zte_wifi_control.py ~/.config/zte-wifi-timer.env
```

Lo script installerà queste due esecuzioni in crontab:

- `0 0 * * *` → Wi-Fi OFF
- `0 7 * * *` → Wi-Fi ON

Log: `/var/log/zte-wifi-timer.log`

## Note

- Alcuni firmware ZTE usano varianti diverse del payload di login: lo script prova più combinazioni comuni.
- Se il tuo firmware usa parametri diversi, apri gli strumenti sviluppatore del browser mentre fai login/toggle Wi-Fi e adatta i payload in `zte_wifi_control.py`.
