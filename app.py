from flask import Flask, render_template, request, session, redirect, url_for, send_file
from datetime import datetime
import sqlite3
import socket
import json
import math
from functools import wraps
from openpyxl import Workbook
import io

app = Flask(__name__)
app.secret_key = 'clave-secreta-cambiar-esto'

ADMIN_USUARIO = 'admin'
ADMIN_CONTRASENA = '1234'

UMBRAL_RECONOCIMIENTO = 0.6

def conectar_bd():
    conexion = sqlite3.connect('asistencia.db')
    conexion.row_factory = sqlite3.Row
    return conexion

def distancia_euclidiana(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))

def requiere_login(f):
    @wraps(f)
    def funcion_protegida(*args, **kwargs):
        if not session.get('es_admin'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return funcion_protegida

# ---------- INICIO ----------

@app.route('/')
def inicio():
    return render_template('inicio.html')

@app.route('/estudiante')
def estudiante_landing():
    return render_template('estudiante.html')

# ---------- REGISTRO ----------

@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        nombre = request.form['nombre']
        apellido_paterno = request.form['apellido_paterno']
        apellido_materno = request.form['apellido_materno']
        edad = request.form['edad']
        curso = request.form['curso']
        tipo_sangre = request.form['tipo_sangre']
        descriptor_facial = request.form.get('descriptor_facial')

        if not descriptor_facial:
            return render_template('registro.html', error='Debes capturar tu rostro antes de registrarte')

        conexion = conectar_bd()
        cursor = conexion.cursor()

        cursor.execute('''
            SELECT id FROM estudiantes
            WHERE nombre = ? AND apellido_paterno = ? AND apellido_materno = ?
        ''', (nombre, apellido_paterno, apellido_materno))
        existente = cursor.fetchone()

        if existente:
            conexion.close()
            return render_template('registro.html', error='Ya existe un estudiante registrado con ese nombre')

        cursor.execute('''
            INSERT INTO estudiantes (nombre, apellido_paterno, apellido_materno, edad, curso, tipo_sangre, descriptor_facial)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (nombre, apellido_paterno, apellido_materno, edad, curso, tipo_sangre, descriptor_facial))
        conexion.commit()
        conexion.close()

        return render_template('registro_exitoso.html', nombre=nombre)

    return render_template('registro.html', error=None)

@app.route('/buscar-qr', methods=['GET', 'POST'])
def buscar_qr():
    if request.method == 'POST':
        nombre = request.form['nombre']
        apellido_paterno = request.form['apellido_paterno']
        apellido_materno = request.form['apellido_materno']

        conexion = conectar_bd()
        cursor = conexion.cursor()
        cursor.execute('''
            SELECT id, nombre, curso FROM estudiantes
            WHERE nombre = ? AND apellido_paterno = ? AND apellido_materno = ?
        ''', (nombre, apellido_paterno, apellido_materno))
        estudiante = cursor.fetchone()
        conexion.close()

        if estudiante:
            return render_template('registro_exitoso.html', nombre=estudiante['nombre'])
        else:
            return render_template('buscar_qr.html', error='No se encontró ningún estudiante con esos datos.')

    return render_template('buscar_qr.html', error=None)

# ---------- LOGIN ADMIN ----------

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usuario = request.form['usuario']
        contrasena = request.form['contrasena']
        if usuario == ADMIN_USUARIO and contrasena == ADMIN_CONTRASENA:
            session['es_admin'] = True
            return redirect(url_for('admin'))
        return render_template('login.html', error='Usuario o contraseña incorrectos')
    return render_template('login.html', error=None)

@app.route('/logout')
def logout():
    session.pop('es_admin', None)
    return redirect(url_for('login'))

# ---------- VISTA ADMIN ----------

@app.route('/admin')
@requiere_login
def admin():
    return render_template('admin.html')

@app.route('/admin/<int:curso>')
@requiere_login
def admin_curso(curso):
    return render_template('admin_curso.html', curso=curso)

@app.route('/admin/<int:curso>/tomar-asistencia')
@requiere_login
def tomar_asistencia(curso):
    return render_template('tomar_asistencia.html', curso=curso)

@app.route('/admin/reporte-faltas')
@requiere_login
def reporte_faltas():
    conexion = conectar_bd()
    cursor = conexion.cursor()
    hoy = datetime.now().strftime('%Y-%m-%d')

    cursor.execute('SELECT * FROM estudiantes ORDER BY curso, nombre')
    todos = cursor.fetchall()

    faltaron = []
    for est in todos:
        cursor.execute('SELECT id FROM asistencias WHERE estudiante_id = ? AND fecha = ?', (est['id'], hoy))
        if not cursor.fetchone():
            faltaron.append(est)

    conexion.close()
    return render_template('reporte_faltas.html', faltaron=faltaron, fecha=hoy)

# ---------- API ----------

@app.route('/api/curso/<int:curso>')
@requiere_login
def api_curso(curso):
    conexion = conectar_bd()
    cursor = conexion.cursor()

    fecha_consultada = request.args.get('fecha')
    if not fecha_consultada:
        fecha_consultada = datetime.now().strftime('%Y-%m-%d')

    cursor.execute('SELECT * FROM estudiantes WHERE curso = ?', (curso,))
    estudiantes = cursor.fetchall()

    resultado = []
    for est in estudiantes:
        cursor.execute('''
            SELECT hora FROM asistencias WHERE estudiante_id = ? AND fecha = ?
            ORDER BY hora DESC LIMIT 1
        ''', (est['id'], fecha_consultada))
        asistencia = cursor.fetchone()
        resultado.append({
            'id': est['id'],
            'nombre': est['nombre'],
            'apellido_paterno': est['apellido_paterno'],
            'apellido_materno': est['apellido_materno'],
            'hora': asistencia['hora'] if asistencia else None
        })

    conexion.close()
    return {'estudiantes': resultado, 'fecha': fecha_consultada}

@app.route('/api/reconocer', methods=['POST'])
@requiere_login
def reconocer():
    datos = request.get_json()
    descriptor_recibido = datos.get('descriptor')
    curso = datos.get('curso')

    if not descriptor_recibido:
        return {'exito': False, 'mensaje': 'No se recibió ningún rostro'}, 400

    conexion = conectar_bd()
    cursor = conexion.cursor()
    cursor.execute('SELECT * FROM estudiantes WHERE curso = ? AND descriptor_facial IS NOT NULL', (curso,))
    estudiantes = cursor.fetchall()

    mejor_estudiante = None
    mejor_distancia = None

    for est in estudiantes:
        descriptor_guardado = json.loads(est['descriptor_facial'])
        distancia = distancia_euclidiana(descriptor_recibido, descriptor_guardado)
        if mejor_distancia is None or distancia < mejor_distancia:
            mejor_distancia = distancia
            mejor_estudiante = est

    if mejor_estudiante is None or mejor_distancia > UMBRAL_RECONOCIMIENTO:
        conexion.close()
        return {'exito': False, 'mensaje': 'No se reconoció a ningún estudiante de este curso'}

    ahora = datetime.now()
    fecha = ahora.strftime('%Y-%m-%d')
    hora = ahora.strftime('%H:%M:%S')

    cursor.execute('INSERT INTO asistencias (estudiante_id, curso, fecha, hora) VALUES (?, ?, ?, ?)',
                   (mejor_estudiante['id'], curso, fecha, hora))
    conexion.commit()
    conexion.close()

    return {
        'exito': True,
        'nombre': mejor_estudiante['nombre'] + ' ' + mejor_estudiante['apellido_paterno'],
        'hora': hora
    }

@app.route('/exportar/<int:curso>')
@requiere_login
def exportar_curso(curso):
    conexion = conectar_bd()
    cursor = conexion.cursor()
    hoy = datetime.now().strftime('%Y-%m-%d')

    cursor.execute('SELECT * FROM estudiantes WHERE curso = ?', (curso,))
    estudiantes = cursor.fetchall()

    libro = Workbook()
    hoja = libro.active
    hoja.title = f'Curso {curso}'
    hoja.append(['Nombre', 'Apellido Paterno', 'Apellido Materno', 'Edad', 'Tipo de Sangre', 'Hora de asistencia'])

    for est in estudiantes:
        cursor.execute('SELECT hora FROM asistencias WHERE estudiante_id = ? AND fecha = ? ORDER BY hora DESC LIMIT 1',
                       (est['id'], hoy))
        asistencia = cursor.fetchone()
        hora = asistencia['hora'] if asistencia else 'Ausente'
        hoja.append([est['nombre'], est['apellido_paterno'], est['apellido_materno'], est['edad'], est['tipo_sangre'], hora])

    conexion.close()

    archivo = io.BytesIO()
    libro.save(archivo)
    archivo.seek(0)

    return send_file(archivo, as_attachment=True,
                      download_name=f'curso_{curso}_{hoy}.xlsx',
                      mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

def obtener_ip_local():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

if __name__ == '__main__':
    ip = obtener_ip_local()
    print(f'\n>>> Abre en el navegador: https://{ip}:5000\n')
    app.run(debug=True, host='0.0.0.0', port=5000, ssl_context='adhoc')