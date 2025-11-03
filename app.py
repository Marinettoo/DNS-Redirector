# Importamos las librerías necesarias
from flask import Flask, redirect, request  # Flask para el servidor web; request para ver la petición entrante
import dns.resolver  # dnspython: para consultar registros DNS

# Creamos la aplicación Flask
app = Flask(__name__)

# Definimos una ruta para todas las peticiones al dominio (path '/')
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def redirector(path):
    # Obtenemos el nombre de host de la petición (ej. 'drive.marinettoo.es')
    # request.host puede incluir el puerto, así que lo cortamos
    host = request.host.split(':')[0]  

    # Realizamos una consulta DNS para obtener el registro TXT del host
    try:
        answers = dns.resolver.resolve(host, 'TXT')
    except Exception as e:
        # Si hay un error (por ejemplo, registro no existe), devolvemos un mensaje
        return f"Error al consultar DNS: {e}", 404

    # Extraemos el contenido del registro TXT (puede haber varios bloques)
    url_destino = None
    for rdata in answers:
        for txt_string in rdata.strings:
            # dns.resolver devuelve bytes, los decodificamos a texto
            url_destino = txt_string.decode('utf-8')
            break
        if url_destino:
            break

    # Si encontramos una URL en el TXT, redirigimos al usuario
    if url_destino:
        return redirect(url_destino, code=302)
    else:
        return "No se encontró URL de destino en el registro TXT.", 404

# Ponemos el servidor en modo de escucha. host='0.0.0.0' hace que sea accesible externamente.
if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=False)
