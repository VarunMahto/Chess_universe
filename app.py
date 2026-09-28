import os, secrets, hashlib, hmac, json, time, asyncio
from datetime import datetime, date
from typing import Optional
import chess
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Header, UploadFile, File
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import create_engine, String, Integer, Date, DateTime, Text, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

BASE_DIR=os.path.dirname(os.path.abspath(__file__))
STATIC_DIR=os.path.join(BASE_DIR,"static")
DATABASE_URL=os.getenv("DATABASE_URL", "sqlite:///"+os.path.join(BASE_DIR,"chess_arcade.db"))
if DATABASE_URL.startswith("postgres://"): DATABASE_URL=DATABASE_URL.replace("postgres://","postgresql+psycopg://",1)
if DATABASE_URL.startswith("postgresql://"): DATABASE_URL=DATABASE_URL.replace("postgresql://","postgresql+psycopg://",1)
engine=create_engine(DATABASE_URL,pool_pre_ping=True,connect_args={"check_same_thread":False} if DATABASE_URL.startswith("sqlite") else {})
SessionLocal=sessionmaker(bind=engine,expire_on_commit=False)
class Base(DeclarativeBase): pass
class Player(Base):
    __tablename__="players"
    id:Mapped[int]=mapped_column(Integer,primary_key=True)
    name:Mapped[str]=mapped_column(String(80))
    email:Mapped[str]=mapped_column(String(255),unique=True,index=True)
    password_hash:Mapped[str]=mapped_column(String(255))
    birth_date:Mapped[date]=mapped_column(Date)
    skill_level:Mapped[str]=mapped_column(String(40),default="beginner")
    coins:Mapped[int]=mapped_column(Integer,default=0)
    games_played:Mapped[int]=mapped_column(Integer,default=0)
    wins:Mapped[int]=mapped_column(Integer,default=0)
    losses:Mapped[int]=mapped_column(Integer,default=0)
    draws:Mapped[int]=mapped_column(Integer,default=0)
    rating:Mapped[int]=mapped_column(Integer,default=1000)
    streak:Mapped[int]=mapped_column(Integer,default=0)
    best_streak:Mapped[int]=mapped_column(Integer,default=0)
    unlocked_boards:Mapped[str]=mapped_column(Text,default='["Classic"]')
    selected_board:Mapped[str]=mapped_column(String(40),default="Classic")
    created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
class LoginSession(Base):
    __tablename__="sessions"
    token:Mapped[str]=mapped_column(String(128),primary_key=True)
    player_id:Mapped[int]=mapped_column(Integer,index=True)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
class GameRecord(Base):
    __tablename__="games"
    id:Mapped[int]=mapped_column(Integer,primary_key=True)
    player_id:Mapped[int]=mapped_column(Integer,index=True)
    mode:Mapped[str]=mapped_column(String(20))
    result:Mapped[str]=mapped_column(String(20))
    color:Mapped[str]=mapped_column(String(10),default="white")
    opponent:Mapped[str]=mapped_column(String(80),default="")
    moves:Mapped[str]=mapped_column(Text,default="[]")
    played_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
class ProfileExtra(Base):
    __tablename__="profile_extras"
    player_id:Mapped[int]=mapped_column(Integer,ForeignKey("players.id"),primary_key=True)
    country:Mapped[str]=mapped_column(String(2),default="IN")
    player_code:Mapped[str]=mapped_column(String(24),unique=True,index=True)
    avatar_type:Mapped[str]=mapped_column(String(20),default="preset")
    avatar_value:Mapped[str]=mapped_column(Text,default="king")
    profile_image:Mapped[str]=mapped_column(Text,default="")
    xp:Mapped[int]=mapped_column(Integer,default=0)
    level:Mapped[int]=mapped_column(Integer,default=1)
    peak_rating:Mapped[int]=mapped_column(Integer,default=1000)
    mission_state:Mapped[str]=mapped_column(Text,default="{}")
class Clan(Base):
    __tablename__="clans"
    id:Mapped[int]=mapped_column(Integer,primary_key=True)
    name:Mapped[str]=mapped_column(String(50),unique=True)
    code:Mapped[str]=mapped_column(String(12),unique=True,index=True)
    owner_id:Mapped[int]=mapped_column(Integer,ForeignKey("players.id"))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
class ClanMember(Base):
    __tablename__="clan_members"
    id:Mapped[int]=mapped_column(Integer,primary_key=True)
    clan_id:Mapped[int]=mapped_column(Integer,ForeignKey("clans.id"))
    player_id:Mapped[int]=mapped_column(Integer,ForeignKey("players.id"))
class ClanMessage(Base):
    __tablename__="clan_messages"
    id:Mapped[int]=mapped_column(Integer,primary_key=True)
    clan_id:Mapped[int]=mapped_column(Integer,ForeignKey("clans.id"))
    player_id:Mapped[int]=mapped_column(Integer,ForeignKey("players.id"))
    text:Mapped[str]=mapped_column(Text)
    sent_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
class FriendRequest(Base):
    __tablename__="friend_requests"
    id:Mapped[int]=mapped_column(Integer,primary_key=True)
    from_id:Mapped[int]=mapped_column(Integer,ForeignKey("players.id"))
    to_id:Mapped[int]=mapped_column(Integer,ForeignKey("players.id"))
    status:Mapped[str]=mapped_column(String(20),default="pending")
    created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
class Activity(Base):
    __tablename__="activities"
    id:Mapped[int]=mapped_column(Integer,primary_key=True)
    player_id:Mapped[int]=mapped_column(Integer,index=True)
    kind:Mapped[str]=mapped_column(String(40))
    amount:Mapped[int]=mapped_column(Integer,default=1)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
Base.metadata.create_all(engine)
app=FastAPI(title="Chess Arcade")

@app.middleware("http")
async def no_cache(request, call_next):
    response=await call_next(request)
    if request.url.path=="/" or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"]="no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"]="no-cache"
        response.headers["Expires"]="0"
    return response
app.mount("/static",StaticFiles(directory=STATIC_DIR),name="static")

class Register(BaseModel):
    name:str=Field(min_length=1,max_length=80)
    email:EmailStr
    password:str=Field(min_length=8,max_length=128)
    birth_date:date
    skill_level:str=Field(default="beginner",max_length=40)
    country:str=Field(default="IN",min_length=2,max_length=2)
class Login(BaseModel): email:EmailStr; password:str
class BoardPick(BaseModel): board:str
class Purchase(BaseModel): board:str
class SkillPick(BaseModel): skill_level:str
class RecordGame(BaseModel): mode:str; result:str; color:str="white"; opponent:str=""; moves:list[str]=[]

THEMES={
    "Classic":(0,"#efe5c6","#769656"),"Midnight":(50,"#d4d9df","#526579"),"Emerald":(100,"#e3edcf","#4d7658"),
    "Royal":(150,"#eee0bb","#674d7c"),"Carbon":(200,"#d9d9d9","#3f4650"),"Ocean":(250,"#dceaf0","#3c6e91"),
    "Sunset":(300,"#f4dfbd","#b85f4f"),"Amethyst":(400,"#eadcf0","#72508b"),"Obsidian":(500,"#bfc3c8","#252a30"),
    "Aurora":(650,"#e0efdf","#4d7f72"),"Royal Gold":(800,"#f0e0a5","#876c2e"),"Crimson":(1000,"#f1d2d2","#8e3c46")
}

def hp(p):
    salt=secrets.token_bytes(16); d=hashlib.pbkdf2_hmac("sha256",p.encode(),salt,240000); return f"pbkdf2$240000${salt.hex()}${d.hex()}"
def vp(p,s):
    try:
        _,r,sh,dh=s.split("$"); d=hashlib.pbkdf2_hmac("sha256",p.encode(),bytes.fromhex(sh),int(r)); return hmac.compare_digest(d.hex(),dh)
    except Exception:return False

def extra_for(db,pid):
    e=db.query(ProfileExtra).filter(ProfileExtra.player_id==pid).first()
    if not e:
        code="CA"+secrets.token_hex(6).upper(); e=ProfileExtra(player_id=pid,player_code=code); db.add(e); db.commit(); db.refresh(e)
    return e
def rank_for_peak(r):
    return "wood" if r<1000 else "bronze" if r<1200 else "silver" if r<1600 else "gold" if r<2000 else "diamond" if r<2400 else "master" if r<2500 else "grandmaster"
def pub(p):
    with SessionLocal() as db:
        e=extra_for(db,p.id)
        return {"id":p.id,"name":p.name,"email":p.email,"birth_date":p.birth_date.isoformat(),"skill_level":p.skill_level,
        "coins":p.coins,"games_played":p.games_played,"wins":p.wins,"losses":p.losses,"draws":p.draws,
        "rating":p.rating,"elo_rating":p.rating,"streak":p.streak,"best_streak":p.best_streak,
        "unlocked_boards":json.loads(p.unlocked_boards or '["Classic"]'),"selected_board":p.selected_board,
        "country":e.country,"player_code":e.player_code,"avatar_type":e.avatar_type,"avatar_value":e.avatar_value,
        "profile_image":e.profile_image,"xp":e.xp,"level":e.level,"peak_rating":e.peak_rating,"rank":rank_for_peak(e.peak_rating),"mission_state":e.mission_state,
        "clan": clan_info(db,p.id)}
def clan_info(db,pid):
    m=db.query(ClanMember).filter(ClanMember.player_id==pid).first()
    if not m:return None
    c=db.get(Clan,m.clan_id); return {"id":c.id,"name":c.name,"code":c.code,"owner_id":c.owner_id,"members":db.query(ClanMember).filter(ClanMember.clan_id==c.id).count()}
def player_from_auth(auth):
    if not auth or not auth.lower().startswith("bearer "): raise HTTPException(401,"Login required.")
    with SessionLocal() as db:
        s=db.get(LoginSession,auth.split(" ",1)[1].strip())
        if not s: raise HTTPException(401,"Session expired.")
        p=db.get(Player,s.player_id)
        if not p: raise HTTPException(401,"Player not found.")
        return p

@app.get("/")
def home(): return FileResponse(os.path.join(STATIC_DIR,"index.html"))
@app.get("/health")
def health(): return {"ok":True}
@app.post("/api/register")
def register(x:Register):
    if x.birth_date>date.today(): raise HTTPException(400,"Birth date cannot be in the future.")
    skill=x.skill_level if x.skill_level in {"beginner","rules","strategy","tournament"} else "beginner"
    with SessionLocal() as db:
        email=x.email.lower().strip()
        if db.query(Player).filter(Player.email==email).first(): raise HTTPException(409,"An account with this email already exists.")
        p=Player(name=x.name.strip(),email=email,password_hash=hp(x.password),birth_date=x.birth_date,skill_level=skill)
        db.add(p); db.commit(); db.refresh(p)
        code="CA"+secrets.token_hex(6).upper()
        db.add(ProfileExtra(player_id=p.id,country=x.country.upper(),player_code=code,peak_rating=1000)); db.commit()
        t=secrets.token_urlsafe(48); db.add(LoginSession(token=t,player_id=p.id)); db.commit()
        return {"token":t,"player":pub(p)}
@app.post("/api/login")
def login(x:Login):
    with SessionLocal() as db:
        p=db.query(Player).filter(Player.email==x.email.lower().strip()).first()
        if not p or not vp(x.password,p.password_hash): raise HTTPException(401,"Incorrect email or password.")
        t=secrets.token_urlsafe(48); db.add(LoginSession(token=t,player_id=p.id)); db.commit(); return {"token":t,"player":pub(p)}
@app.post("/api/logout")
def logout(authorization:Optional[str]=Header(None)):
    if authorization and authorization.lower().startswith("bearer "):
        with SessionLocal() as db:
            s=db.get(LoginSession,authorization.split(" ",1)[1].strip())
            if s: db.delete(s); db.commit()
    return {"ok":True}
@app.get("/api/me")
def me(authorization:Optional[str]=Header(None)): return pub(player_from_auth(authorization))
@app.post("/api/profile/skill")
def skill(x:SkillPick,authorization:Optional[str]=Header(None)):
    p=player_from_auth(authorization)
    if x.skill_level not in {"beginner","rules","strategy","tournament"}: raise HTTPException(400,"Invalid skill level.")
    with SessionLocal() as db:
        q=db.get(Player,p.id); q.skill_level=x.skill_level; db.commit(); return pub(q)
@app.post("/api/profile/board")
def select_board(x:BoardPick,authorization:Optional[str]=Header(None)):
    p=player_from_auth(authorization)
    with SessionLocal() as db:
        q=db.get(Player,p.id); owned=json.loads(q.unlocked_boards or '["Classic"]')
        if x.board not in owned: raise HTTPException(403,"Board is not unlocked.")
        q.selected_board=x.board; db.commit(); return pub(q)
@app.post("/api/profile/purchase")
def purchase(x:Purchase,authorization:Optional[str]=Header(None)):
    p=player_from_auth(authorization)
    if x.board not in THEMES: raise HTTPException(400,"Unknown board.")
    with SessionLocal() as db:
        q=db.get(Player,p.id); owned=json.loads(q.unlocked_boards or '["Classic"]')
        if x.board in owned: q.selected_board=x.board
        else:
            price=THEMES[x.board][0]
            if q.coins<price: raise HTTPException(400,"Not enough coins.")
            q.coins-=price; owned.append(x.board); q.unlocked_boards=json.dumps(owned); q.selected_board=x.board
        db.commit(); return pub(q)
@app.get("/api/games")
def games(authorization:Optional[str]=Header(None)):
    p=player_from_auth(authorization)
    with SessionLocal() as db:
        rows=db.query(GameRecord).filter(GameRecord.player_id==p.id).order_by(GameRecord.played_at.desc()).limit(30).all()
        return [{"mode":r.mode,"result":r.result,"color":r.color,"opponent":r.opponent,"moves":json.loads(r.moves or "[]"),"played_at":r.played_at.isoformat()} for r in rows]
@app.post("/api/games")
def record_game(x:RecordGame,authorization:Optional[str]=Header(None)):
    p=player_from_auth(authorization)
    if x.mode not in {"offline","computer","online"} or x.result not in {"win","loss","draw"}: raise HTTPException(400,"Invalid game record.")
    reward=0
    with SessionLocal() as db:
        q=db.get(Player,p.id); q.games_played+=1
        e=extra_for(db,q.id); e.xp += 40 + (60 if x.result=="win" else 15 if x.result=="draw" else 5); e.peak_rating=max(e.peak_rating,q.rating)
        if x.result=="win":
            q.wins+=1; q.streak+=1; q.best_streak=max(q.best_streak,q.streak); q.rating+=12
            e.peak_rating=max(e.peak_rating,q.rating)
            e.level=max(1,1+e.xp//500)
            if x.mode in {"computer","online"}: q.coins+=20; reward=20
        elif x.result=="loss":
            q.losses+=1; q.streak=0; q.rating=max(100,q.rating-8)
            e.level=max(1,1+e.xp//500)
            if x.mode=="online": q.coins=max(0,q.coins-10); reward=-10
        else:
            q.draws+=1; q.streak=0; q.rating+=2
            e.peak_rating=max(e.peak_rating,q.rating); e.level=max(1,1+e.xp//500)
            if x.mode in {"computer","online"}: q.coins+=5; reward=5
        st=mission_state(e); a=st["activity"]; a["moves"]=int(a.get("moves",0))+len(x.moves); a["online"] = int(a.get("online",0)) + (1 if x.mode=="online" else 0); a["onlineWins"] = int(a.get("onlineWins",0)) + (1 if x.mode=="online" and x.result=="win" else 0); a["timed"] = int(a.get("timed",0)) + (1 if "clock" in x.mode.lower() else 0); st["activity"]=a; e.mission_state=json.dumps(st)
        db.add(GameRecord(player_id=q.id,mode=x.mode,result=x.result,color=x.color,opponent=x.opponent,moves=json.dumps(x.moves[:500])))
        db.commit(); return {"player":pub(q),"reward":reward}

class ProfileUpdate(BaseModel):
    avatar_type:str; avatar_value:str
class CountryPick(BaseModel): country:str
class PlayerSearch(BaseModel): code:str
class FriendReq(BaseModel): player_id:int
class ClanCreate(BaseModel): name:str
class ClanJoin(BaseModel): code:str
class ClanSay(BaseModel): text:str
class MissionClaim(BaseModel): mission_id:int; phase:int
class ActivityIn(BaseModel): kind:str; amount:int=1
class FriendRespond(BaseModel): request_id:int; accept:bool

@app.post("/api/profile/avatar")
def profile_avatar(x:ProfileUpdate,authorization:Optional[str]=Header(None)):
    p=player_from_auth(authorization)
    if x.avatar_type not in {"preset","image"}: raise HTTPException(400,"Invalid avatar type.")
    if x.avatar_type=="preset" and x.avatar_value not in {"king","queen","knight","rook","bishop","pawn","dragon","robot","wizard","ninja","fox","tiger"}: raise HTTPException(400,"Invalid avatar.")
    with SessionLocal() as db:
        e=extra_for(db,p.id); e.avatar_type=x.avatar_type; e.avatar_value=x.avatar_value; db.commit(); return pub(db.get(Player,p.id))

@app.post("/api/profile/country")
def profile_country(x:CountryPick,authorization:Optional[str]=Header(None)):
    p=player_from_auth(authorization)
    with SessionLocal() as db:
        e=extra_for(db,p.id); e.country=x.country.upper()[:2]; db.commit(); return pub(db.get(Player,p.id))

@app.post("/api/profile/image")
async def profile_image(file:UploadFile=File(...),authorization:Optional[str]=Header(None)):
    p=player_from_auth(authorization); data=await file.read()
    if len(data)>2*1024*1024: raise HTTPException(400,"Image must be under 2 MB.")
    if not (file.content_type or "").startswith("image/"): raise HTTPException(400,"Please upload an image.")
    import base64
    encoded=f"data:{file.content_type};base64,"+base64.b64encode(data).decode()
    with SessionLocal() as db:
        e=extra_for(db,p.id); e.avatar_type="image"; e.avatar_value=encoded; db.commit(); return pub(db.get(Player,p.id))

@app.get("/api/player/search")
def player_search(code:str,authorization:Optional[str]=Header(None)):
    player_from_auth(authorization)
    with SessionLocal() as db:
        e=db.query(ProfileExtra).filter(ProfileExtra.player_code==code.upper().strip()).first()
        if not e: raise HTTPException(404,"Player not found.")
        p=db.get(Player,e.player_id); return {"id":p.id,"name":p.name,"country":e.country,"player_code":e.player_code,"rating":p.rating,"elo_rating":p.rating,"rank":rank_for_peak(e.peak_rating),"level":e.level,"avatar_type":e.avatar_type,"avatar_value":e.avatar_value}

@app.post("/api/friends/request")
def friend_request(x:FriendReq,authorization:Optional[str]=Header(None)):
    p=player_from_auth(authorization)
    with SessionLocal() as db:
        if not db.get(Player,x.player_id) or x.player_id==p.id: raise HTTPException(400,"Invalid player.")
        exists=db.query(FriendRequest).filter(FriendRequest.from_id==p.id,FriendRequest.to_id==x.player_id).first()
        if exists:return {"ok":True,"status":exists.status}
        db.add(FriendRequest(from_id=p.id,to_id=x.player_id)); db.commit(); e=extra_for(db,p.id); st=mission_state(e); st["activity"]["friendRequests"]=int(st["activity"].get("friendRequests",0))+1; e.mission_state=json.dumps(st); db.commit(); return {"ok":True,"status":"pending"}

@app.get("/api/friends/requests")
def friend_requests(authorization:Optional[str]=Header(None)):
    p=player_from_auth(authorization)
    with SessionLocal() as db:
        rows=db.query(FriendRequest).filter(FriendRequest.to_id==p.id,FriendRequest.status=="pending").all(); out=[]
        for r in rows:
            q=db.get(Player,r.from_id); e=extra_for(db,q.id); out.append({"id":r.id,"name":q.name,"country":e.country,"player_code":e.player_code,"rating":q.rating})
        return out
@app.post("/api/friends/respond")
def friend_respond(x:FriendRespond,authorization:Optional[str]=Header(None)):
    p=player_from_auth(authorization)
    with SessionLocal() as db:
        r=db.get(FriendRequest,x.request_id)
        if not r or r.to_id!=p.id: raise HTTPException(404,"Request not found.")
        r.status="accepted" if x.accept else "rejected"; db.commit(); return {"ok":True,"status":r.status}

@app.get("/api/friends")
def friends(authorization:Optional[str]=Header(None)):
    p=player_from_auth(authorization)
    with SessionLocal() as db:
        rows=db.query(FriendRequest).filter(((FriendRequest.from_id==p.id)|(FriendRequest.to_id==p.id)),FriendRequest.status=="accepted").all(); out=[]
        for r in rows:
            oid=r.to_id if r.from_id==p.id else r.from_id; q=db.get(Player,oid); e=extra_for(db,oid); out.append({"name":q.name,"player_code":e.player_code,"rating":q.rating})
        return out

@app.post("/api/clan/create")
def clan_create(x:ClanCreate,authorization:Optional[str]=Header(None)):
    p=player_from_auth(authorization)
    with SessionLocal() as db:
        if db.query(Clan).filter(Clan.name==x.name.strip()).first(): raise HTTPException(409,"Clan name already exists.")
        code=secrets.token_hex(4).upper(); c=Clan(name=x.name.strip()[:50],code=code,owner_id=p.id); db.add(c); db.commit(); db.refresh(c); db.add(ClanMember(clan_id=c.id,player_id=p.id)); db.commit(); e=extra_for(db,p.id); st=mission_state(e); st["activity"]["clanJoin"]=int(st["activity"].get("clanJoin",0))+1; e.mission_state=json.dumps(st); db.commit(); return clan_info(db,p.id)

@app.post("/api/clan/join")
def clan_join(x:ClanJoin,authorization:Optional[str]=Header(None)):
    p=player_from_auth(authorization)
    with SessionLocal() as db:
        c=db.query(Clan).filter(Clan.code==x.code.upper().strip()).first()
        if not c: raise HTTPException(404,"Clan not found.")
        if db.query(ClanMember).filter(ClanMember.clan_id==c.id,ClanMember.player_id==p.id).first(): return clan_info(db,p.id)
        if db.query(ClanMember).filter(ClanMember.clan_id==c.id).count()>=10: raise HTTPException(400,"Clan is full.")
        db.add(ClanMember(clan_id=c.id,player_id=p.id)); db.commit(); e=extra_for(db,p.id); st=mission_state(e); st["activity"]["clanJoin"]=int(st["activity"].get("clanJoin",0))+1; e.mission_state=json.dumps(st); db.commit(); return clan_info(db,p.id)

@app.get("/api/clan/chat")
def clan_chat(authorization:Optional[str]=Header(None)):
    p=player_from_auth(authorization)
    with SessionLocal() as db:
        ci=clan_info(db,p.id)
        if not ci:return []
        rows=db.query(ClanMessage).filter(ClanMessage.clan_id==ci["id"]).order_by(ClanMessage.sent_at.desc()).limit(50).all(); return [{"name":db.get(Player,r.player_id).name,"text":r.text,"sent_at":r.sent_at.isoformat()} for r in reversed(rows)]

@app.post("/api/clan/chat")
def clan_say(x:ClanSay,authorization:Optional[str]=Header(None)):
    p=player_from_auth(authorization)
    with SessionLocal() as db:
        ci=clan_info(db,p.id)
        if not ci: raise HTTPException(400,"Join a clan first.")
        db.add(ClanMessage(clan_id=ci["id"],player_id=p.id,text=x.text[:500])); db.commit(); return {"ok":True}

MISSION_TARGETS=[[1,3,5],[5,10,20],[10,20,40],[1,3,5],[3,5,10],[5,10,20],[10,20,30],[3,5,10],[5,10,15],[10,15,25],[1,5,10],[5,10,20],[10,20,40],[1,3,5],[3,5,10],[1,2,3],[3,5,10],[1,2,3],[1,2,3],[1,2,3],[1,2,3],[1,2,3],[1,3,5],[1,3,5],[1,3,10],[1,3,10],[1,3,10],[1,2,5],[1,3,10],[20,30,50],[15,20,30],[1,3,5],[3,5,10],[1050,1100,1200],[1100,1200,1400],[1200,1400,1600],[1400,1600,1800],[1600,1800,2000],[2,5,10],[2,5,10],[3,5,10],[5,10,20],[10,20,30],[1,3,5],[1,3,10],[1,3,10],[1,3,10],[1,2,3],[3,5,10],[5,10,15]]
def mission_state(e):
    try: st=json.loads(e.mission_state or '{}')
    except Exception: st={}
    if 'claimed' not in st: st={'claimed':{str(k):int(v) for k,v in st.items() if str(k).isdigit()},'activity':{}}
    st.setdefault('claimed',{}); st.setdefault('activity',{})
    return st
def activity_value(db,p,e,kind):
    st=mission_state(e); return int(st['activity'].get(kind,0))
def mission_value(db,p,e,i):
    vals=[p.games_played,activity_value(db,p,e,'moves'),activity_value(db,p,e,'moves'),p.wins,p.games_played,p.games_played,p.games_played,p.wins,p.wins,p.wins,activity_value(db,p,e,'captures'),activity_value(db,p,e,'captures'),activity_value(db,p,e,'captures'),activity_value(db,p,e,'checks'),activity_value(db,p,e,'checks'),activity_value(db,p,e,'castles'),activity_value(db,p,e,'castles'),activity_value(db,p,e,'promotions'),activity_value(db,p,e,'winQ'),activity_value(db,p,e,'winR'),activity_value(db,p,e,'winB'),activity_value(db,p,e,'winN'),activity_value(db,p,e,'timed'),activity_value(db,p,e,'timedWins'),activity_value(db,p,e,'online'),activity_value(db,p,e,'onlineWins'),activity_value(db,p,e,'public'),activity_value(db,p,e,'private'),activity_value(db,p,e,'friends'),p.games_played,p.wins,p.draws,p.draws,p.rating,p.rating,p.rating,p.rating,p.rating,len(json.loads(p.unlocked_boards or '[]')),max(0,len(json.loads(p.unlocked_boards or '[]'))-1),activity_value(db,p,e,'puzzles'),activity_value(db,p,e,'puzzles'),activity_value(db,p,e,'puzzles'),activity_value(db,p,e,'lessons'),activity_value(db,p,e,'friendRequests'),1 if clan_info(db,p.id) else 0,activity_value(db,p,e,'clanMessages'),activity_value(db,p,e,'rematches'),p.streak,p.level]
    return vals[i] if i < len(vals) else 0
@app.post("/api/activity")
def activity(x:ActivityIn,authorization:Optional[str]=Header(None)):
    p=player_from_auth(authorization)
    allowed={'moves','captures','checks','castles','promotions','winQ','winR','winB','winN','timed','timedWins','online','onlineWins','public','private','friends','puzzles','lessons','friendRequests','clanMessages','rematches'}
    if x.kind not in allowed: raise HTTPException(400,'Unknown activity.')
    with SessionLocal() as db:
        q=db.get(Player,p.id); e=extra_for(db,q.id); st=mission_state(e); st['activity'][x.kind]=int(st['activity'].get(x.kind,0))+max(1,min(100,x.amount)); e.mission_state=json.dumps(st); db.commit(); return pub(q)
@app.post("/api/missions/claim")
def mission_claim(x:MissionClaim,authorization:Optional[str]=Header(None)):
    p=player_from_auth(authorization)
    if not (0<=x.mission_id<len(MISSION_TARGETS) and 1<=x.phase<=3): raise HTTPException(400,'Invalid mission.')
    with SessionLocal() as db:
        q=db.get(Player,p.id); e=extra_for(db,q.id); st=mission_state(e); claimed=int(st['claimed'].get(str(x.mission_id),0))
        if x.phase!=claimed+1: raise HTTPException(400,'Complete the previous phase first.')
        value=mission_value(db,q,e,x.mission_id); target=MISSION_TARGETS[x.mission_id][x.phase-1]
        if value<target: raise HTTPException(400,f'Phase {x.phase} is not complete yet. Target: {target}.')
        reward=20+(x.phase-1)*15; q.coins+=reward; e.xp+=25+x.phase*10; e.level=max(1,1+e.xp//500); st['claimed'][str(x.mission_id)]=x.phase; e.mission_state=json.dumps(st); db.commit(); return {'player':pub(q),'reward':reward,'phase':x.phase}
@app.get("/api/rules")
def rules():
    return {"rules":["Pawns move forward and capture diagonally.","Knights move in an L shape and jump.","Bishops move diagonally.","Rooks move horizontally or vertically.","Queens combine rook and bishop movement.","Kings move one square and cannot move into check.","Castling has king/rook conditions.","En passant is a special pawn capture.","Promotion lets a pawn become a queen, rook, bishop or knight.","Checkmate ends the game; stalemate is a draw.","Threefold repetition, the 50-move rule and insufficient material can draw a game."]}

# ---------------- online rooms ----------------
rooms={}; matches={}; PUBLIC_QUEUE=[]; ROOM_TTL=600

def new_code():
    alphabet="ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    while True:
        code="".join(secrets.choice(alphabet) for _ in range(6))
        if code not in rooms:return code
def choose_colors(a,b):
    if a in {"white","black"}: return a,"black" if a=="white" else "white"
    if b in {"white","black"}: return "black" if b=="white" else "white",b
    return ("white","black") if secrets.randbelow(2)==0 else ("black","white")
def compatible(a,b): return a["timed"]==b["timed"] and (not a["timed"] or a["seconds"]==b["seconds"])
async def send(ws,msg):
    try: await ws.send_json(msg)
    except Exception: pass
async def close_room(code):
    r=rooms.pop(code,None)
    if r:
        await send(r["host"],{"type":"room_closed","message":"Room closed."})
async def reaper():
    while True:
        await asyncio.sleep(10); now=time.monotonic()
        for code,r in list(rooms.items()):
            if len(r["players"])<2 and now-r["created"]>=ROOM_TTL: await close_room(code)
@app.on_event("startup")
async def startup(): asyncio.create_task(reaper())

def sync_clock(m):
    if not m["timed"] or m["finished"]: return
    side="white" if m["board"].turn==chess.WHITE else "black"; now=time.monotonic(); m["clocks"][side]=max(0,m["clocks"][side]-(now-m["last_tick"])); m["last_tick"]=now
def clock_payload(m): sync_clock(m); return {"white_seconds":m["clocks"]["white"],"black_seconds":m["clocks"]["black"]}
async def start_match(first, second, code, timed, seconds):
    c1,c2=choose_colors(first.get("preference","random"),second.get("preference","random")); board=chess.Board()
    m={"players":[first["ws"],second["ws"]],"colors":{first["ws"]:c1,second["ws"]:c2},"names":{first["ws"]:first["name"],second["ws"]:second["name"]},"countries":{first["ws"]:first.get("country","IN"),second["ws"]:second.get("country","IN")},"board":board,"timed":timed,"clocks":{"white":float(seconds),"black":float(seconds)},"last_tick":time.monotonic(),"finished":False,"room_code":code,"moves":[]}
    for p in m["players"]: matches[p]=m
    await send(first["ws"],{"type":"start","color":c1,"opponent":second["name"],"room_code":code,"timed":timed,"country":m["countries"][first["ws"]],"opponent_country":m["countries"][second["ws"]],**clock_payload(m)})
    await send(second["ws"],{"type":"start","color":c2,"opponent":first["name"],"room_code":code,"timed":timed,"country":m["countries"][second["ws"]],"opponent_country":m["countries"][first["ws"]],**clock_payload(m)})
    return m
async def match_queue(waiter):
    for other in list(PUBLIC_QUEUE):
        if other["ws"] is waiter["ws"]: continue
        if compatible(other,waiter):
            PUBLIC_QUEUE.remove(other)
            return await start_match(other,waiter,new_code(),waiter["timed"],waiter["seconds"])
    PUBLIC_QUEUE.append(waiter); return None

@app.websocket("/ws")
async def websocket(ws:WebSocket):
    await ws.accept(); current_room=None
    try:
        while True:
            d=await ws.receive_json(); typ=d.get("type")
            if typ=="create_room":
                seconds=max(1,min(86399,int(d.get("seconds",300))))
                r={"code":new_code(),"private":bool(d.get("private",True)),"timed":bool(d.get("timed",False)),"seconds":seconds,"created":time.monotonic(),"host":ws,"players":[{"ws":ws,"name":str(d.get("name","Player"))[:40],"preference":d.get("preference","random"),"country":d.get("country","IN")}]}
                rooms[r["code"]]=r; current_room=r["code"]
                await send(ws,{"type":"room_created","code":r["code"],"private":r["private"],"expires_in":ROOM_TTL})
                if not r["private"]:
                    for waiter in list(PUBLIC_QUEUE):
                        if compatible(r,waiter): PUBLIC_QUEUE.remove(waiter); rooms.pop(r["code"],None); current_room=r["code"]; await start_match(r["players"][0],waiter,r["code"],r["timed"],r["seconds"]); break
            elif typ=="toggle_room":
                r=rooms.get(d.get("code"))
                if not r or r["host"] is not ws: await send(ws,{"type":"error","message":"Only the host can change privacy."}); continue
                r["private"]=not r["private"]; await send(ws,{"type":"room_privacy","private":r["private"]})
                if not r["private"]:
                    for waiter in list(PUBLIC_QUEUE):
                        candidate={"timed":r["timed"],"seconds":r["seconds"]}
                        if compatible(r,waiter):
                            PUBLIC_QUEUE.remove(waiter); rooms.pop(r["code"],None); await start_match(r["players"][0],waiter,r["code"],r["timed"],r["seconds"]); break
            elif typ=="join_room":
                code="".join(c for c in str(d.get("code","")).upper() if c.isalnum()); r=rooms.get(code)
                if not r: await send(ws,{"type":"error","message":"Room not found or closed."}); continue
                if len(r["players"])>=2: await send(ws,{"type":"error","message":"Room is full."}); continue
                second={"ws":ws,"name":str(d.get("name","Player"))[:40],"preference":d.get("preference","random"),"country":d.get("country","IN")}; first=r["players"][0]; r["players"].append(second); rooms.pop(code,None); current_room=code
                await start_match(first,second,code,r["timed"],r["seconds"])
            elif typ=="join_public":
                waiter={"ws":ws,"name":str(d.get("name","Player"))[:40],"preference":d.get("preference","random"),"timed":bool(d.get("timed",False)),"seconds":max(1,min(86399,int(d.get("seconds",300)))),"country":d.get("country","IN") }
                m=await match_queue(waiter)
                if m is None: await send(ws,{"type":"waiting_public","message":"Searching for an opponent…"})
            elif typ=="move":
                m=matches.get(ws)
                if not m or m["finished"]: continue
                if m["timed"]:
                    sync_clock(m); side="white" if m["board"].turn else "black"
                    if m["clocks"][side]<=0:
                        m["finished"]=True; winner="black" if side=="white" else "white"
                        for p in m["players"]: await send(p,{"type":"timeout","winner":winner,**clock_payload(m)})
                        continue
                color=chess.WHITE if m["colors"][ws]=="white" else chess.BLACK
                try: mv=chess.Move.from_uci(d.get("uci",""))
                except Exception: await send(ws,{"type":"error","message":"Invalid move."}); continue
                if m["board"].turn!=color or mv not in m["board"].legal_moves: await send(ws,{"type":"error","message":"Illegal move."}); continue
                m["board"].push(mv); m["moves"].append(mv.uci()); m["last_tick"]=time.monotonic()
                for p in m["players"]: await send(p,{"type":"move","uci":mv.uci(),**clock_payload(m)})
                if m["board"].is_game_over():
                    m["finished"]=True; out=m["board"].outcome(); winner="draw" if out.winner is None else ("white" if out.winner else "black")
                    for p in m["players"]: await send(p,{"type":"result","winner":winner,**clock_payload(m)})
            elif typ=="timeout":
                m=matches.get(ws)
                if not m or not m["timed"] or m["finished"]: continue
                sync_clock(m); side="white" if m["board"].turn else "black"
                if d.get("side")!=side or m["clocks"][side]>0: continue
                m["finished"]=True; winner="black" if side=="white" else "white"
                for p in m["players"]: await send(p,{"type":"timeout","winner":winner,**clock_payload(m)})
            elif typ=="resign":
                m=matches.get(ws)
                if not m or m["finished"]: continue
                side=m["colors"][ws]; winner="black" if side=="white" else "white"; m["finished"]=True
                for p in m["players"]: await send(p,{"type":"result","winner":winner,"reason":"resignation",**clock_payload(m)})
            elif typ=="draw_offer":
                m=matches.get(ws)
                if m and not m["finished"]:
                    for p in m["players"]:
                        if p is not ws: await send(p,{"type":"draw_offer","from":m["names"][ws]})
            elif typ=="draw_accept":
                m=matches.get(ws)
                if m and not m["finished"]:
                    m["finished"]=True
                    for p in m["players"]: await send(p,{"type":"result","winner":"draw","reason":"agreement",**clock_payload(m)})
            elif typ=="leave":
                if current_room in rooms: await close_room(current_room); current_room=None
                m=matches.pop(ws,None)
                if m:
                    for p in m["players"]:
                        matches.pop(p,None)
                        if p is not ws: await send(p,{"type":"opponent_left"})
                return
    except WebSocketDisconnect: pass
    finally:
        PUBLIC_QUEUE[:]=[x for x in PUBLIC_QUEUE if x["ws"] is not ws]
        if current_room in rooms: await close_room(current_room)
        m=matches.pop(ws,None)
        if m:
            for p in m["players"]:
                matches.pop(p,None)
                if p is not ws: await send(p,{"type":"opponent_left"})

if __name__=="__main__":
    import uvicorn
    port=int(os.getenv("CHESS_PORT","8010")); print(f"Chess Arcade server starting at http://127.0.0.1:{port}")
    uvicorn.run(app,host="127.0.0.1",port=port)
