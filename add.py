#━━━━━━━━━━━━━━━━━
#DESCORD : @meropvp
#TELEGRAM : @meropvp
#INSTGRAM : @mero4dev
#CHANNEL : @loginbp
#GROUP : @loginbpchat
#WORKING IN ALL SERVER + AUTO UPDATE
#━━━━━━━━━━━━━━━━━

import time
import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import os
from google_play_scraper import app

U, P = "7936114203", "5625B7987D1AAACF19A7AE11682717BA045CC3773D3C899B3B715B75ADF40B4B"
obb = requests.get("https://version.ffmax.purplevioleto.com/live/ver.php?lang=ar&device=android").json()['latest_release_version']
version = app('com.dts.freefireth')['version']

servers = {
    "ME": "https://clientbp.ggpolarbear.com/",
    "IND": "https://client.ind.freefiremobile.com/",
    "ID": "https://clientbp.ggpolarbear.com/",
    "BR": "https://client.us.freefiremobile.com/",
    "VN": "https://clientbp.ggpolarbear.com/",
    "TH": "https://clientbp.ggpolarbear.com/",
    "CIS": "https://clientbp.ggpolarbear.com/",
    "BD": "https://clientbp.ggpolarbear.com/",
    "PK": "https://clientbp.ggpolarbear.com/",
    "SG": "https://clientbp.ggpolarbear.com/",
    "NA": "https://client.us.freefiremobile.com/",
    "SAC": "https://client.us.freefiremobile.com/",
    "EU": "https://clientbp.ggpolarbear.com/",
    "TW": "https://clientbp.ggpolarbear.com/",
}

print("ME, ID, BR, IND, VN, TH, CIS, BD, PK, SG, NA, SAC, EU, TW")
server = input("server : ").upper()
os.system('clear')

xnxx = servers.get(server)
if not xnxx:
    print("err in server name :)")
    exit()


print("1- add\n2- remove")
pornhub = input()
if pornhub == "1":
    url = f"{xnxx}RequestAddingFriend"
elif pornhub == "2":
    url = f"{xnxx}RemoveFriend"
else:
    exit()

os.system('clear')
jwt = requests.get(f"https://ff-jwt-gen-api.lovable.app/api/public/token?uid={U}&password={P}").json()['token']
acc = requests.get(f"https://ff-jwt-gen-api.lovable.app/api/public/token?uid={U}&password={P}").json()['account_id']
print(obb)
print(jwt)
time.sleep(2)
os.system('clear')
id = input("id : ")

def buildpacket(fd):
    pk = bytearray()
    for f, v in fd.items():
        ev = []
        n = (f << 3) | (2 if isinstance(v, (dict, str, bytes)) else 0)
        while True:
            b = n & 0x7F; n >>= 7
            if n: b |= 0x80
            ev.append(b)
            if not n: break
        pk.extend(bytes(ev))
        
        if isinstance(v, int):
            ev2 = []
            while True:
                b = v & 0x7F; v >>= 7
                if v: b |= 0x80
                ev2.append(b)
                if not v: break
            pk.extend(bytes(ev2))
    return pk

payload = buildpacket({1: int(acc), 2: int(id), 3: 22}).hex()
key = bytes([89, 103, 38, 116, 99, 37, 68, 69, 117, 104, 54, 37, 90, 99, 94, 56])
iv = bytes([54, 111, 121, 90, 68, 114, 50, 50, 69, 51, 121, 99, 104, 106, 77, 37])
enc = bytes.fromhex(AES.new(key, AES.MODE_CBC, iv).encrypt(pad(bytes.fromhex(payload), 16)).hex())

hr = {
    "Accept": "*/*", 
    "Accept-Encoding": "deflate, gzip", 
    "Content-Type": "application/x-www-form-urlencoded",
    "Authorization": f"Bearer {jwt}", 
    "ReleaseVersion": obb,
    "User-Agent": "UnityPlayer/2022.3.47f1 (UnityWebRequest/1.0, libcurl/8.5.0-DEV)",  
    "X-GA": "v1 1", 
    "X-Unity-Version": "2022.3.47f1",
    "Content-Length": str(len(enc))
}

rQ = requests.post(url, headers=hr, data=enc)
print(rQ.status_code)