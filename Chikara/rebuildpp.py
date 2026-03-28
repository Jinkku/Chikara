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
cursor.execute("SELECT * FROM users")
users = cursor.fetchall()
step = 0.02
for user in users:
    cursor.execute(f"SELECT * FROM scores WHERE username = '" + str(user["username"]) + "' ORDER BY points DESC")
    co = cursor.fetchall()
    per = 1
    pp = 0
    x = 0
    for score in co:
        print(user["username"])
        print(score["beatmapname"])
        cursor.execute(f"SELECT * FROM beatmaps WHERE beatmapid = " + str(score["beatmap_id"]))
        beatmap = cursor.fetchone()
        if score["replay_path"] != None and beatmap != None and os.path.isfile(storage_root + str(score["replay_path"])):
            print("found")
            mult=getmult(score["mods"], speed=score["speed_multi"])
            info = ppv2calc.calculate_ppv2(storage_root + score["replay_path"], storage_root + beatmap["chartfile"])
            pp += info.pp * per
            per -= step
            if per < 0 or x > 30:
                break
            x += 1
        
    cursor.execute("UPDATE users SET ranked_points = "+str(int(pp))+" WHERE id = " + str(user["id"]))

cursor.close()
conn.close()