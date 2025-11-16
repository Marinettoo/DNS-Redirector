# Importamos todas las librerías necesarias
import os
import requests
import hashlib
import json
from flask import Flask, render_template, request, redirect
from dotenv import load_dotenv
import dns.resolver

# === Cargar variables del .env ===
# (Asegúrate de que tu .env en la ruta absoluta ~/redirector_AUTO/.env está correcto)
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

API_KEY = os.getenv("IONOS_API_KEY")
ZONE_ID = os.getenv("IONOS_ZONE_ID")
DOMAIN = os.getenv("BASE_DOMAIN") # (marinettoo.es)
SERVER_PUBLIC_IP = os.getenv("SERVER_PUBLIC_IP") # (62.37.101.123)
IONOS_API_BASE = "https://api.hosting.ionos.com/dns/v1"

app = Flask(__name__, template_folder="templates")

# Comprobación de variables de entorno al inicio
if not all([API_KEY, ZONE_ID, SERVER_PUBLIC_IP, DOMAIN]):
    print("❌ ERROR: Faltan variables de entorno (API_KEY, ZONE_ID, SERVER_PUBLIC_IP o BASE_DOMAIN) en ~/redirector_AUTO/.env")
    exit()


def generar_hash(url):
    """Genera hash corto a partir de la URL"""
    return hashlib.md5(url.encode()).hexdigest()[:6]


def crear_registro_ionos(subdominio, tipo, contenido):
    """
    Función genérica para crear un registro (A o TXT) en IONOS DNS.
    Usa el método POST al endpoint /records (¡La lógica correcta que SÍ funciona!).
    """
    headers = {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    # 🎯 ¡LA CORRECCIÓN! El 'name' debe ser el FQDN (ej. hash.marinettoo.es)
    fqdn = f"{subdominio}.{DOMAIN}"

    # El payload es una lista con un diccionario.
    payload = [
        {
            "name": fqdn,
            "type": tipo,
            "content": contenido,
            "ttl": 3600,
            "prio": 0, # Necesario para TXT, ignorado para A
            "disabled": False
        }
    ]

    # 🎯 ¡LA CORRECCIÓN! Usamos POST al endpoint /records
    endpoint = f"{IONOS_API_BASE}/zones/{ZONE_ID}/records"
    
    print(f"⚙️ Intentando crear registro: POST {endpoint}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    
    response = requests.post(endpoint, headers=headers, json=payload)
    
    print(f"Respuesta de IONOS (Status: {response.status_code}):")
    try:
        print(json.dumps(response.json(), indent=2))
    except Exception:
        print(response.text)
        
    return response


def obtener_txt_record(subdominio_fqdn):
    """
    Lee el registro TXT desde DNS público (como dig).
    Acepta el FQDN completo (ej. 75170f.marinettoo.es)
    """
    try:
        print(f"🔎 Buscando TXT para: {subdominio_fqdn}")
        
        resolver = dns.resolver.Resolver()
        # Apuntamos a un resolver público conocido para saltar la caché local
        resolver.nameservers = ['8.8.8.8'] 
        
        answers = resolver.resolve(subdominio_fqdn, 'TXT')
        
        for rdata in answers:
            # Unimos todos los strings del registro TXT
            full_text = b"".join(rdata.strings).decode('utf-8')
            print(f"✅ TXT encontrado: {full_text}")
            return full_text
            
    except Exception as e:
        print(f"❌ Error leyendo TXT: {e}")
    return None

# ===============================================
# RUTA PRINCIPAL (PANEL DE CONTROL O REDIRECCIÓN)
# ===============================================
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def panel_o_redirigir(path):
    
    # Obtenemos el host con el que el usuario ha llegado (ej. "75170f.marinettoo.es:8080")
    host = request.host.split(':')[0] # Quitamos el puerto

    # -----------------------------------------------------------
    # Escenario B: El usuario visita el DOMINIO BASE o una IP (¡Mostrar Panel!)
    # -----------------------------------------------------------
    # 🎯 ¡CORREGIDO! Si el host es el dominio base O una IP, mostramos el panel.
    if host == DOMAIN or host == SERVER_PUBLIC_IP or host == "127.0.0.1" or host.startswith("192.168."):
        print(f"Host es el dominio base o una IP ({host}). Sirviendo index.html...")
        # (Asegúrate de que tienes el archivo en la ruta absoluta ~/redirector_AUTO/templates/index.html)
        return render_template("index.html")

    # -----------------------------------------------------------
    # Escenario A: El usuario visita un SUBDOMINIO (¡Redirigir!)
    # -----------------------------------------------------------
    else:
        
        print(f"Ruta de redirección activada para el HOST: {host}")
        destino = obtener_txt_record(host)

        if destino:
            print(f"Redirigiendo a: {destino}")
            return redirect(destino, code=302)
        else:
            print("No se encontró destino.")
            # Evitamos el error del favicon.ico que vimos en el log
            if host.startswith("favicon.ico"):
                return "No hay favicon", 404
                
            return f"""
            <h3>❌ No se encontró registro TXT para: {host}</h3>
            <p>Asegúrate de que el DNS se ha propagado (tarda unos minutos).</p>
            """, 404

    # -----------------------------------------------------------
    # Escenario B: El usuario visita el DOMINIO BASE (¡Mostrar Panel!)
    # -----------------------------------------------------------
    # ¡¡¡ESTE BLOQUE 'ELSE' ES EL ERROR!!! ¡LO BORRAMOS!
    # else:
    #     print("Host es el dominio base. Sirviendo index.html...")
    #     # (Asegúrate de que tienes el archivo en la ruta absoluta ~/redirector_AUTO/templates/index.html)
    #     return render_template("index.html")


# ===============================================
# RUTA PARA CREAR (La que usa el formulario)
# ===============================================
@app.route("/crear", methods=["POST"])
def crear():
    url_larga = request.form.get("url", "").strip()
    # 🎯 ¡NUEVO! Leemos el subdominio personalizado del formulario
    subdominio_opcional = request.form.get("subdominio_personalizado", "").strip().lower()

    if not url_larga.startswith(("http://", "https://")):
        return "⚠️ La URL debe empezar por http:// o https://", 400

    # 🎯 ¡NUEVO! Lógica para decidir el nombre del subdominio
    if subdominio_opcional:
        # Validación simple: solo letras y números, y no más de 25 caracteres
        # (DNS tiene límites, evitemos nombres inválidos)
        if not subdominio_opcional.isalnum() or len(subdominio_opcional) > 25:
            return "⚠️ El subdominio personalizado solo puede contener letras y números (sin espacios ni guiones) y máx. 25 caracteres.", 400
        codigo = subdominio_opcional
        print(f"Usando subdominio personalizado: {codigo}")
    else:
        codigo = generar_hash(url_larga)
        print(f"Usando hash generado: {codigo}")
    
    # --- 🎯 PASO 1: Crear REGISTRO A ---
    resp_a = crear_registro_ionos(codigo, "A", SERVER_PUBLIC_IP)
    
    if resp_a.status_code not in (200, 201, 202):
        try:
            detalle = json.dumps(resp_a.json(), indent=2)
        except Exception:
            detalle = resp_a.text
        return f"""
        <h3>❌ Error al crear el REGISTRO A</h3>
        <p>Status: {resp_a.status_code}</p>
        <pre>{detalle}</pre>
        """, 500

    # --- 🎯 PASO 2: Crear REGISTRO TXT ---
    resp_txt = crear_registro_ionos(codigo, "TXT", url_larga)

    if resp_txt.status_code in (200, 201, 202):
        
        enlace_corto = f"http://{codigo}.{DOMAIN}"
        
        return f"""
        <h2>✅ Registros creados correctamente</h2>
        <p><b>Subdominio:</b> {codigo}</p>
        <p><b>Registro A:</b> {codigo}.{DOMAIN} -> {SERVER_PUBLIC_IP}</p>
        <p><b>Registro TXT:</b> {codigo}.{DOMAIN} -> "{url_larga}"</p>
        <hr>
        <p><b>Enlace corto (tardará unos minutos en propagarse):</b></p>
        <p><a href="{enlace_corto}" target="_blank">{enlace_corto}</a></p>
        """
    else:
        try:
            detalle = json.dumps(resp_txt.json(), indent=2)
        except Exception:
            detalle = resp_txt.text
        return f"""
        <h3>❌ Error al crear el REGISTRO TXT</h3>
        <p>Status: {resp_txt.status_code}</p>
        <pre>{detalle}</pre>
        """, 500

# ===============================================
# INICIAR EL SERVIDOR
# ===============================================
if __name__ == "__main__":
    print(f"Iniciando servidor. Panel en http://{DOMAIN}:8080")
    app.run(host="0.0.0.0", port=8080, debug=True)
