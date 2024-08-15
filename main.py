import datetime
import hashlib
from fastapi import FastAPI, HTTPException
import requests
from flask import Response
import psycopg2
import os

app = FastAPI()
idx = 0
urls = {}

def get_db_connection():
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    return conn


@app.post("/shorten")
async def create_short_url(url: str):
    try:
        # url validation
        response = requests.get(url, timeout=5)
        if 200 <= response.status_code < 400:
            global idx, urls
            idx += 1
            code = hashlib.md5(url.encode()).hexdigest()
            code = code[:6]
            created_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S %p")
            expiration_date = (datetime.datetime.now() + datetime.timedelta(days=69)).strftime("%Y-%m-%d %H:%M:%S %p")

            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM urls WHERE short_code = %s", (code,))
            existing_url = cursor.fetchone()
            if existing_url is not None:
                raise HTTPException(status_code=409, detail="Short code already exists: {}".format(code))

            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO urls (short_code, original_url, created_at, last_updated_at, expiration_date, access_count) VALUES (%s, %s, %s, %s, %s, %s)",
                (code, url, created_at, created_at, expiration_date, 0))
            conn.commit()
            cursor.close()
            conn.close()

            urls[code] = {
                    "id" : idx,
                    "short_code": code, # 'b7bf24'
                    "original_url": url,
                    "created_at": created_at, # 2021-09-01 12:00:00 PM
                    "last_updated_at": created_at,
                    "expiration_date": expiration_date,
                    "access_count": 0,
            }
            return urls[code]
        else:
            raise HTTPException(status_code=404, detail="Invalid URL")
    except requests.exceptions.RequestException:
        raise HTTPException(status_code=404, detail="An error occurred while validating the URL, please try again later")


@app.get("/shorten/{short_code}")
async def get_original_url(short_code: str):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM urls WHERE short_code = %s", (short_code,))
        result = cursor.fetchone()
        cursor.close()
        conn.close()

        if not result:
            raise HTTPException(status_code=404, detail="Short code not found")

        expiration_date = result[5]
        if expiration_date < datetime.datetime.now():
            await delete_short_url(short_code)
            raise HTTPException(status_code=404, detail="Short code has expired")

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE urls SET access_count = access_count + 1 WHERE short_code = %s", (short_code,))
        conn.commit()
        cursor.close()
        conn.close()

        return {
            "short_code": result[1],
            "original_url": result[2],
            "created_at": result[3],
            "last_updated_at": result[4],
            "expiration_date": result[5],
            "access_count": result[6] + 1
        }

    except psycopg2.Error as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")


@app.put("/shorten")
async def update_short_url(short_code: str, url: str):
    try:
        if short_code not in urls:
            raise HTTPException(status_code=404, detail="Short code not found")

        if urls[short_code]["expiration_date"] < datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S %p"):
            urls.pop(short_code)
            raise HTTPException(status_code=404, detail="Short code has expired")

        urls[short_code]["original_url"] = url
        urls[short_code]["last_updated_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S %p")
        urls[short_code]["access_count"] = 0
        return urls[short_code]

    except requests.exceptions.RequestException:
        raise HTTPException(status_code=404, detail="An error occurred while updating the short URL, please try again later")


@app.delete("/shorten/{short_code}")
async def delete_short_url(short_code: str):
    try:
        if short_code not in urls:
            raise HTTPException(status_code=404, detail="Short code not found")

        urls.pop(short_code)
        return Response(status=204, headers={"message": "Short URL deleted successfully"})

    except requests.exceptions.RequestException:
        raise HTTPException(status_code=404, detail="An error occurred while deleting the short URL, please try again later")