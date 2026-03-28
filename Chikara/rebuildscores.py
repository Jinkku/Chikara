import mysql.connector,os
import ppv2calc
import zipfile
modsaliasab='AT','DT','HT','SL','BT','RND','NF' # Mods Alias
def getmult(multiplier,submit=False, speed = 1):
    if not submit:
        try:
            multiplier=float(multiplier)
            #multiplier=1
            newmodsys=0
        except Exception:
            fulltmp=multiplier
            multiplier=1
            newmodsys=1
    else:
        return multiplier
        newmodsys=1
        multiplier=1
    if newmodsys:
       for a in modsaliasab:
            if a in str(fulltmp):
               if a=='BT':
                  multiplier*=1.15
               elif a == 'DT':
                  multiplier*=1.15 / ( speed / 1.25 )
               elif a == 'HT':
                  multiplier*=0.3 / ( speed / 0.5 )
               elif a == 'NF':
                  multiplier*=0.5
               elif not a in ('AT','RND'):
                  multiplier+=0.5
    return multiplier
conn = mysql.connector.connect(
    host="localhost",
    port=3306,
    database="qluta",
    user="qluta",
    password="Qlutaismyfav$23",
)
storage_root = "/Storage/Chikara/"
cursor = conn.cursor(dictionary=True)
conn.autocommit = True
cursor.execute("SELECT * FROM scores")
scores = cursor.fetchall()
for score in scores:
    cursor.execute(f"SELECT * FROM beatmaps WHERE beatmapid = " + str(score["beatmap_id"]))
    co = cursor.fetchone()
    if co != None:
        cursor.execute("UPDATE scores SET ranked = " + str(co["ranked"]) + " WHERE beatmap_id = " + str(co["beatmapid"]))
        #print("ranked")
        print(score["username"])
        print(score["beatmapname"])
        if score["replay_path"] != None and os.path.isfile(storage_root + str(score["replay_path"])):
            
            print("found")
            mult=getmult(score["mods"], speed=score["speed_multi"])
            info = ppv2calc.calculate_ppv2(storage_root + score["replay_path"], storage_root + co["chartfile"])
            cursor.execute("UPDATE scores SET points = " + str(info.pp * mult) + " WHERE beatmap_id = " + str(co["beatmapid"]) + " AND id = " + str(score["id"]))
            cursor.execute("UPDATE scores SET maxpoints = " + str(info.max_pp * mult) + " WHERE beatmap_id = " + str(co["beatmapid"]) + " AND id = " + str(score["id"]))
        else:
            print("none")
            cursor.execute("UPDATE scores SET points = 0 WHERE beatmap_id = " + str(co["beatmapid"]) + " AND id = " + str(score["id"]))
            cursor.execute("UPDATE scores SET maxpoints = " + str(co["pp"]) + " WHERE beatmap_id = " + str(co["beatmapid"]) + " AND id = " + str(score["id"]))
    else:
        print("unranked")
        cursor.execute("UPDATE scores SET ranked = 0 WHERE beatmap_id = " + str(score["beatmap_id"]) + " AND id = " + str(score["id"]))

cursor.close()
conn.close()