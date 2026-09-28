"""
Script de introspección de SOLO LECTURA.
Lee el esquema de una tabla desde INFORMATION_SCHEMA de SQL Server.
Uso: python inspect_schema.py <nombre_tabla>
"""
import sys
from database import get_db_connection


def inspect_table(table_name: str):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                c.ORDINAL_POSITION,
                c.COLUMN_NAME,
                c.DATA_TYPE,
                c.CHARACTER_MAXIMUM_LENGTH,
                c.NUMERIC_PRECISION,
                c.NUMERIC_SCALE,
                c.IS_NULLABLE,
                c.COLUMN_DEFAULT
            FROM INFORMATION_SCHEMA.COLUMNS c
            WHERE c.TABLE_NAME = ?
            ORDER BY c.ORDINAL_POSITION
            """,
            [table_name],
        )
        rows = cursor.fetchall()
        if not rows:
            print(f"No se encontraron columnas para la tabla '{table_name}'.")
            return

        # Llaves primarias
        cursor.execute(
            """
            SELECT ku.COLUMN_NAME
            FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
            JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE ku
                ON tc.CONSTRAINT_NAME = ku.CONSTRAINT_NAME
            WHERE tc.CONSTRAINT_TYPE = 'PRIMARY KEY' AND tc.TABLE_NAME = ?
            """,
            [table_name],
        )
        pks = {r[0] for r in cursor.fetchall()}

        print(f"# Tabla: {table_name}")
        print(f"# Total columnas: {len(rows)}")
        print(f"# PK: {sorted(pks) if pks else '(ninguna)'}\n")
        print(f"{'#':>3}  {'COLUMNA':<32} {'TIPO':<18} {'LEN':>6} {'NULL':<5} PK")
        print("-" * 80)
        for r in rows:
            pos, name, dtype, char_len, num_prec, num_scale, is_null, default = r
            length = char_len if char_len is not None else (
                f"{num_prec},{num_scale}" if num_prec is not None else ""
            )
            pk_mark = "PK" if name in pks else ""
            print(f"{pos:>3}  {name:<32} {dtype:<18} {str(length):>6} {is_null:<5} {pk_mark}")
    finally:
        conn.close()


if __name__ == "__main__":
    table = sys.argv[1] if len(sys.argv) > 1 else "imclient"
    inspect_table(table)
