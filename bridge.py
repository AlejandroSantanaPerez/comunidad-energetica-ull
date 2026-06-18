import paho.mqtt.client as mqtt
from influxdb import InfluxDBClient
import datetime

# Configuración
MQTT_BROKER = "mosquitto"
INFLUX_HOST = "influx_db"
DB_NAME = "tfm_energia"

print(f"[{datetime.datetime.now()}] Iniciando el Bridge...")

# Conexión a InfluxDB
try:
    client_db = InfluxDBClient(host=INFLUX_HOST, port=8086)
    client_db.create_database(DB_NAME)
    print(f"[{datetime.datetime.now()}] Conectado a InfluxDB correctamente.")
except Exception as e:
    print(f"Error conectando a InfluxDB: {e}")

def on_connect(client, userdata, flags, rc, properties=None):
    print(f"[{datetime.datetime.now()}] Conectado al Broker MQTT con código: {rc}")
    # Nos suscribimos aquí para asegurar que tras una reconexión se mantenga
    client.subscribe("shellies/+/emeter/+/+")

def on_message(client, userdata, message):
    try:
        topic = message.topic
        payload = message.payload.decode("utf-8")
        val = float(payload)
        
	# Clasificamos el dato con precisión
        tipo = "desconocido"
        if topic.endswith("/power"): 
            tipo = "potencia_activa_w"  # Solo la potencia real
        elif topic.endswith("/reactive_power"): 
            tipo = "potencia_reactiva_var" # Reactiva aparte
        elif "total" in topic and "returned" not in topic: 
            tipo = "energia_wh"
        elif "voltage" in topic: 
            tipo = "voltaje_v"

        if tipo != "desconocido":
            json_body = [
                {
                    "measurement": tipo,
                    "tags": {
                        "canal": "0" if "/0/" in topic else "1",
                        "dispositivo": topic.split('/')[1]
                    },
                    "fields": {"value": val}
                }
            ]
            client_db.write_points(json_body, database=DB_NAME)
            # Solo imprimimos potencia para no saturar los logs
            if tipo == "potencia_w":
                print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {topic.split('/')[1]} -> {val}W")
            
    except Exception as e:
        pass

# Ajuste para Paho-MQTT v2.0 (Elimina el Warning)
mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message

print(f"[{datetime.datetime.now()}] Conectando al broker {MQTT_BROKER}...")
mqtt_client.connect(MQTT_BROKER, 1883)
mqtt_client.loop_forever()
