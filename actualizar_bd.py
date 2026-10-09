import sqlite3

conexion = sqlite3.connect('asistencia.db')
cursor = conexion.cursor()

try:
    cursor.execute('ALTER TABLE estudiantes ADD COLUMN descriptor_facial TEXT')
    print('Columna descriptor_facial agregada correctamente')
except sqlite3.OperationalError as error:
    print('Aviso:', error)

conexion.commit()
conexion.close()