# HEMS-ULL: Home Energy Management System para Comunidad Energética Universitaria

Este repositorio contiene el código fuente, los scripts de enlace de datos y los archivos de configuración que integran el prototipo de **Sistema Doméstico de Gestión de la Demanda (HEMS)** desarrollado para el Trabajo Fin de Máster (TFM). 

El sistema monitoriza en tiempo real el consumo perimetral de una vivienda mediante un dispositivo hardware **Shelly EM**, cruza dichos registros con curvas de generación fotovoltaica simuladas mediante **PVGIS** bajo la modalidad legal de autoconsumo colectivo, y proporciona un motor de recomendaciones dual (en tiempo real y estratégico) para optimizar la autarquía energética de prosumidores vinculados a la **Universidad de La Laguna (ULL)** dentro del marco del proyecto europeo **SAtComm**.

---

## 🛠️ Estructura del Repositorio

En base al despliegue real en el servidor (`SERVIDOR_TFM`), el proyecto se compone de los siguientes archivos esenciales:

*   **`app.py`**: Aplicación principal y frontend del cuadro de mandos interactivo desarrollado con *Streamlit* y *Plotly*. Almacena la lógica de los paneles de usuario, históricos económicos, balances netos y los sistemas de recomendación.
*   **`bridge.py`**: Script backend encargado del enlace de datos (*bridge*). Escucha asíncronamente las publicaciones de telemetría del Shelly EM a través del protocolo MQTT y persiste las lecturas minutales en el motor de series temporales InfluxDB.
*   **`database_aparatos_nilm.json`**: Base de datos estructurada con las curvas de potencia promedio y tiempos de ciclo caracterizados para electrodomésticos flexibles (lavadora, lavavajillas, secadora, horno), extraídos y validados a partir del conjunto de datos de referencia *AMPds2*.
*   **`perfil_consumo_predeterminado.csv`**: Curvas de demanda horaria tipificadas para modelar el comportamiento base del hogar según el perfil de flexibilidad seleccionado (Piso compartido, Estudiante de mañana, Estudiante de tarde, Hogar tradicional, Trabajo en remoto), adaptadas de *SolarEdge Designer*.
*   **`Timeseries_28.482_-16.306_SA3_5kWp_crystSi_14_26deg_-1deg_2023_2023.csv`**: Registro climatológico minutal y horario de radiación solar extraído de la plataforma oficial *PVGIS* de la Comisión Europea para la ubicación exacta del proyecto piloto.
*   **`docker-compose.yml`**: Archivo de orquestación de contenedores utilizado en el servidor para instanciar e interconectar de forma aislada los servicios de infraestructura de la plataforma (**InfluxDB** y el bróker MQTT **Eclipse Mosquitto**).
*   **`mosquitto.conf`**: Archivo de configuración interna del bróker Mosquitto, parametrizando los puertos de escucha, el almacenamiento de persistencia y las políticas de acceso para la telemetría IoT perimetral.

---

## 🚀 Arquitectura Tecnológica y Requisitos

La plataforma requiere un entorno de ejecución basado en contenedores y un intérprete de Python 3 para los scripts lógicos.

### Requisitos del Sistema (Backend / Cloud)
*   **Docker & Docker Compose** (para el despliegue de la infraestructura base).
*   **Python 3.9+** (entorno de ejecución para los scripts `.py`).

### Dependencias Principales de Python (`requirements.txt`)
*   `streamlit` (Despliegue de la interfaz web interactiva)
*   `plotly` (Renderizado de gráficos analíticos dinámicos de balance neto)
*   `influxdb-client` (Conectividad y persistencia de series temporales)
*   `paho-mqtt` (Suscripción a los flujos telemétricos del Shelly EM)
*   `weasyprint` (Compilación y exportación en caliente de informes de auditoría en PDF)

---

## ⚙️ Instrucciones de Despliegue e Instalación

### 1. Levantar la Infraestructura IoT (Docker)
Para inicializar el bróker MQTT y la base de datos de series temporales en el servidor con los parámetros de contorno predefinidos, ejecute:

```bash
docker-compose up -d
