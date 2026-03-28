import mysql.connector,os
import ppv2calc
import zipfile
conn = mysql.connector.connect(
    host="localhost",
    port=3306,
    database="qluta",
    user="qluta",
    password="Qlutaismyfav$23"
)
storage_root = "/Storage/Chikara/"
cursor = conn.cursor(dictionary=True)
cursor.execute("SELECT * FROM scores")
scores = cursor.fetchall()
for score in scores:
    cursor.execute(f"SELECT * FROM beatmaps WHERE beatmapid = " + str(score["beatmap_id"]))
    co = cursor.fetchone()
    if co != None:
        cursor.execute("UPDATE scores SET ranked = " + str(co["ranked"]) + " WHERE beatmap_id = " + str(co["beatmapid"]))
        if os.path.isfile(storage_root + str(score["replay_path"])):
            info = ppv2calc.calculate_ppv2(storage_root + score["replay_path"], storage_root + co["chartfile"])
            print(info.pp, info.max_pp)
            cursor.execute("UPDATE scores SET points = " + str(info.pp) + " WHERE beatmap_id = " + str(co["beatmapid"]))
            cursor.execute("UPDATE scores SET maxpoints = " + str(info.max_pp) + " WHERE beatmap_id = " + str(co["beatmapid"]))
conn.commit()
cursor.close()
conn.close()