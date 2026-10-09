import sqlite3

conexion = sqlite3.connect('asistencia.db')
cursor = conexion.cursor()

cursor.execute('''
CREATE TABLE IF NOT EXISTS estudiantes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    apellido_paterno TEXT NOT NULL,
    apellido_materno TEXT NOT NULL,
    edad INTEGER NOT NULL,
    curso INTEGER NOT NULL,
    tipo_sangre TEXT NOT NULL
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS asistencias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    estudiante_id INTEGER NOT NULL,
    curso INTEGER NOT NULL,
    fecha TEXT NOT NULL,
    hora TEXT NOT NULL,
    FOREIGN KEY (estudiante_id) REFERENCES estudiantes (id)
)
''')

conexion.commit()
conexion.close()

print('Base de datos creada correctamente')