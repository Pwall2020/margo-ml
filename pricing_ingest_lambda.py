import os, csv, io, json, boto3, datetime
import psycopg2
from psycopg2.extras import execute_values

s3 = boto3.client('s3')
secrets = boto3.client('secretsmanager')

SECRET_ARN = os.environ['DB_SECRET_ARN']

def get_db():
    sec = json.loads(secrets.get_secret_value(SecretId=SECRET_ARN)['SecretString'])
    return psycopg2.connect(
        host=sec['host'], port=sec['port'], dbname=sec['dbname'],
        user=sec['username'], password=sec['password'],
        connect_timeout=5)

def handler(event, context):
    rec = event['Records'][0]
    bucket = rec['s3']['bucket']['name']
    key = rec['s3']['object']['key']

    obj = s3.get_object(Bucket=bucket, Key=key)
    body = obj['Body'].read().decode('utf-8')
    rdr = csv.DictReader(io.StringIO(body))

    rows = []
    names = set()
    for row in rdr:
        name = row['ingredient_name'].strip()
        unit = (row['unit'] or '').strip()
        retailer = (row.get('retailer') or '').strip()
        price_cents = int(row['price_cents'])
        eff = row.get('effective_date') or datetime.date.today().isoformat()
        names.add(name)
        rows.append((name, unit, retailer, price_cents, eff))

    conn = get_db()
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            # map names -> ids (case-insensitive)
            cur.execute("""
              select id, name from ingredients
              where lower(name) = any(%s)
            """, ([n.lower() for n in names],))
            name_to_id = {nm.lower(): _id for _id, nm in cur.fetchall()}

            # split found/missing
            to_upsert = []
            missing = []
            for name, unit, retailer, price_cents, eff in rows:
                ing_id = name_to_id.get(name.lower())
                if not ing_id:
                    missing.append(name)
                    continue
                to_upsert.append((ing_id, unit, retailer or None, price_cents, eff))

            if to_upsert:
                execute_values(cur, """
                  insert into ingredient_prices (ingredient_id, unit, retailer, price_cents, effective_date, source)
                  values %s
                  on conflict (ingredient_id, unit, coalesce(retailer,''), effective_date)
                  do update set price_cents = excluded.price_cents, source = 's3-import'
                """, to_upsert)

        conn.commit()
        return {"status":"ok","upserted":len(to_upsert),"missing":list(set(missing))}
    except Exception as e:
        conn.rollback()
        raise
    finally:
        conn.close()
