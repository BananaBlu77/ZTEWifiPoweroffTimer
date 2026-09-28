# ZTEWifiPoweroffTimer

Script per Raspberry Pi 4 che disattiva e riattiva entrambe le frequenze Wi-Fi di un router ZTE H3601P tramite la console web (`192.168.1.1`). L’automazione usa Playwright per interagire con la pagina, senza chiamare API del router direttamente.

## 1) Installazione

```bash
cd /home/pi/ZTEWifiPoweroffTimer
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium  # solo se non hai già Chrome/Chromium installato
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

Per vedere il browser durante un test aggiungi `--headed`. In caso di errore puoi salvare una schermata con `--screenshot-dir ./diagnostics`.

## Note

- I testi dei menu e delle bande vengono cercati nella pagina: se il firmware è tradotto, adatta le stringhe in `_set_wifi` e `_login`.
- Il percorso predefinito del browser è `/usr/bin/google-chrome`; puoi cambiarlo con `ZTE_BROWSER` o `--browser`.
