"""

龍九控股 Dashboard v5.0.8-flagship

單 authoritative 資料源：framework_snapshot_<DATE>.json

"""

import json
import base64
from datetime import datetime, date

# DEPLOY: 2026-07-13_0100

from pathlib import Path



import streamlit as st

import plotly.express as px



# ============================================================


def _days_left(date_str: str) -> str:
    """Compute remaining days from a date string like '7/20' or '2026-07-20'."""
    if not date_str:
        return ""
    today = date.today()
    for fmt in ("%m/%d", "%Y-%m-%d", "%m-%d", "%Y/%m/%d"):
        try:
            d = datetime.strptime(date_str, fmt).date()
            delta = (d - today).days
            return str(max(delta, 0))
        except ValueError:
            continue
    return ""


# ============================================================

# 0. 頁面設定

# ============================================================

st.set_page_config(

    page_title="龍九控股 Dashboard",

    page_icon="📊",

    layout="wide",

    initial_sidebar_state="expanded",

)



# ============================================================

import json

# DEPLOY: 2026-07-20_0100, base64
EMBEDDED_SNAPSHOT_B64 = "eyJnZW5lcmF0ZWRfYXQiOiAiMjAyNi0wNy0yMFQwMDowMDowMCswODowMCIsICJ2ZXJzaW9uIjogInY1LjAuOS1mbGFnc2hpcC1maXgiLCAiZGF0ZSI6ICIyMDI2LTA3LTIwIiwgInRvdGFsX2Fzc2V0cyI6IDUwNjg5OTMwLCAidG90YWxfbGlhYmlsaXRpZXMiOiAyMjAwMDAwMCwgIm5ldF93b3J0aCI6IDI4Njg5OTMwLCAiZGVidF9yYXRpbyI6ICI0My43JSIsICJtb250aGx5X2luY29tZSI6IDIxODEwMiwgIm1vbnRobHlfZXhwZW5zZSI6IDE0MTk1OCwgIndvcmtpbmdfc3VycGx1cyI6IDc2MTQ0LCAicmV0aXJlbWVudF9zdXJwbHVzIjogMTgxNDIsICJzZWN1cml0aWVzX3RvdGFsX21hcmtldF92YWx1ZSI6IDIzMjg4MzAsICJpbnN1cmFuY2VfbW9udGhseV9kaXZpZGVuZCI6IDY5MDQ0LCAicGFnZTEiOiB7ImFjdHVhbF9jYXNoX2Zsb3ciOiB7ImluY29tZSI6IHsi5Y+w6Zu76Jaq5rC0IjogODIyNjUsICLmiL/np58iOiA4MDEwMCwgIumFjeaBryI6IDgwMDAwLCAi5Yip5oGvIjogMjg1OH0sICJleHBlbnNlIjogeyLmiL/osrgiOiA5OTQ1OCwgIua2iOiyuyI6IDQyMjg3LCAi5rKZ6bm/5oi/56efIjogNDUwMH19LCAidG90YWxfaW5jb21lIjogMjA2MTUyLCAidG90YWxfZXhwZW5zZSI6IDE0MTk1OCwgIndvcmtpbmdfc3VycGx1cyI6IDk5NzM3LCAicmV0aXJlbWVudF9zdXJwbHVzIjogMTI5NzIsICJzdXJwbHVzIjogNzYxNDQsICJydW53YXlfbW9udGhzIjogMjEuMSwgImNvdmVyYWdlX3JhdGlvIjogIjExMy44JSJ9LCAicGFnZTJfYWxsb2NhdGlvbiI6IHsi57O757Wx55uu5qiZIjogeyLlj7DogqEiOiAiMjAlIiwgIue+juiCoSI6ICIyMCUiLCAi6Ziy5a6IIjogIjMwJSIsICLlgrXliLjnj77ph5EiOiAiMjUlIiwgIuingOWvn+e3qeihnSI6ICI1JSIsICLlkIjoqIgiOiAiMTAwJSJ9LCAi5Y+w6IKh5biC5YC85Z6L5oiQ6ZW3IjogeyLmqJnnmoQiOiAiMDA1MCswMDYyMDgrMDA5ODE2IiwgIuW4guWAvCI6IDk0NjY4MCwgIuS9lOavlCI6ICI3LjIlIiwgIue8uuWPoyI6ICItMTIuOCUifSwgIue+juiCoeW4guWAvOWei+aIkOmVtyI6IHsi5qiZ55qEIjogIjAwNjQ2KzAwOTgyMy84MjQr6IGv5Y2aK+iyneiQiuW+tyIsICLluILlgLwiOiA2MDIyMDk1LCAi5L2U5q+UIjogIjQ2LjElIiwgIue8uuWPoyI6ICIrMjYuMSUifSwgIumYsuWuiOWei+mFjeaBryI6IHsi5qiZ55qEIjogIjAwNTYrMDA3MTMrMDA4NzgrMDA5ODFBKzAwOTg0QSswMDkxOSswMDkxOCvlronoga9BSeaUtuebiuaIkOmVtyIsICLluILlgLwiOiAyNTU5MDc3LCAi5L2U5q+UIjogIjE5LjYlIiwgIue8uuWPoyI6ICItMTAuNCUifSwgIuWCteWIuOWPiuePvumHkSI6IHsi5qiZ55qEIjogIumKgOihjOePvumHkStQSU1DTyvnrKzkuIDph5Er5Z+66YeRIiwgIuW4guWAvCI6IDM1NDIyODQsICLkvZTmr5QiOiAiMjcuMSUiLCAi57y65Y+jIjogIisyLjElIn0sICLntZDoq5YiOiAi5Y+w6IKh5LiN6LazLTEyLjgl77yb576O6IKh6LaF5qiZKzI2LjEl77yb6Ziy5a6I5LiN6LazLTEwLjQl77yb6Kq/5bqmPeWKoOeivOWPsOiCoTAwNTEiLCAiaW5kdXN0cnlfZXhwb3N1cmUiOiB7IuWNiuWwjumrlCI6IHsi5biC5YC8IjogNDUwMDAwLCAi5qyK6YeNIjogIjguMiUifSwgIumbu+WtkCI6IHsi5biC5YC8IjogMzIwMDAwLCAi5qyK6YeNIjogIjUuOCUifSwgIkFJL+mbsuerryI6IHsi5biC5YC8IjogODUwMDAwLCAi5qyK6YeNIjogIjE1LjUlIn0sICLph5Hono3kv53pmqoiOiB7IuW4guWAvCI6IDIxMDAwMCwgIuasiumHjSI6ICIzLjglIn0sICLlhaznlKjkuovmpa0vUkVJVHMiOiB7IuW4guWAvCI6IDEyNTAwMCwgIuasiumHjSI6ICIyLjMlIn0sICLlgrXliLgv54++6YeRIjogeyLluILlgLwiOiAzNTQyMjg0LCAi5qyK6YeNIjogIjI3LjElIn0sICLmnKrliIbpoZ4iOiB7IuW4guWAvCI6IDIwMDAwMDAsICLmrIrph40iOiAiMzYuMyUifX19LCAicGFnZTNfaW5zdXJhbmNlX3JlbGF5IjogeyJzeXN0ZW1fdGFyZ2V0IjogeyLlj7DogqHluILlgLzlnovmiJDplbciOiAiMjAlIiwgIue+juiCoeW4guWAvOWei+aIkOmVtyI6ICIyMCUiLCAi6Ziy5a6I5Z6L6YWN5oGvIjogIjMwJSIsICLlgrXliLjlj4rnj77ph5EiOiAiMjUlIiwgIuingOWvny/nt6nooZ0iOiAiNSUiLCAi5ZCI6KiIIjogIjEwMCUifSwgImN1cnJlbnQiOiB7IuWPsOiCoeW4guWAvOWei+aIkOmVtyI6IHsi5qiZ55qEIjogIjAwNTAgKyAwMDYyMDggKyAwMDk4MTYiLCAi5biC5YC8IjogOTQ2NjgwLCAi5L2U5q+UIjogIjcuMiUiLCAi57y65Y+jIjogIi0xMi44JSJ9LCAi576O6IKh5biC5YC85Z6L5oiQ6ZW3IjogeyLmqJnnmoQiOiAiMDA2NDYgKyAwMDk4MjMgKyAwMDk4MjQgKyDoga/ljZrnvo7lnIvmiJDplbcgKyDosp3okIrlvrfkuJbnlYznp5HmioAiLCAi5biC5YC8IjogNjAyMjA5NSwgIuS9lOavlCI6ICI0Ni4xJSIsICLnvLrlj6MiOiAiKzI2LjElIn0sICLpmLLlrojlnovphY3mga8iOiB7IuaomeeahCI6ICIwMDU2ICsgMDA3MTMgKyAwMDg3OCArIDAwOTgxQSArIDAwOTg0QSArIDAwOTE5ICsgMDA5MTggKyDlronoga9BSeaUtuebiuaIkOmVtyIsICLluILlgLwiOiAyNTU5MDc3LCAi5L2U5q+UIjogIjE5LjYlIiwgIue8uuWPoyI6ICItMTAuNCUifSwgIuWCteWIuOWPiuePvumHkSI6IHsi5qiZ55qEIjogIumKgOihjOePvumHkSArIFBJTUNP5pS255uK5aKe6ZW3ICsg56ys5LiA6YeRICsg5Z+66YeRIiwgIuW4guWAvCI6IDM1NDIyODQsICLkvZTmr5QiOiAiMjcuMSUiLCAi57y65Y+jIjogIisyLjElIn19LCAic3VtbWFyeSI6IHsi5Y+w6IKhIjogIuWatOmHjeS4jei2syIsICLnvo7ogqEiOiAi5Zq06YeN6LaF5qiZIiwgIumYsuWuiOmFjeaBryI6ICLkuI3otrMiLCAi6Kq/5bqm5pa55ZCRIjogIuWKoOeivOWPsOiCoe+8iDAwNTHvvInvvIzkuI3lrpzlho3liqDnvo7ogqEv5YK15Yi4In0sICJyZWxheV90cmFja2luZyI6IHsi5pyI5YidIjogeyLmjIHmnIkiOiAi5pGp5qC55aSa6YeN5pS255uK77yIRkozM++8iSIsICLln7rmupbml6UiOiAiNy8wNyIsICLpoJDkvLDlhaXluLMiOiAiNy8xOSIsICLkuIvmrKHnlLPoq4vml6UiOiAi4oCUIn0sICLmnIjkuK0iOiB7IuaMgeaciSI6ICJNJkcg5YWl5oGv5Z+66YeR77yIUUwxODYgKyBRTDE4NO+8iSIsICLln7rmupbml6UiOiAiNy8xNyIsICLpoJDkvLDlhaXluLMiOiAiNy8yOSIsICLkuIvmrKHnlLPoq4vml6UiOiAiNy8xM++8iFQrNO+8iSJ9LCAi5pyI5bqVIjogeyLmjIHmnIkiOiAi5a6J6IGvQUnmlLbnm4rmiJDplbcgKyDosp3okIrlvrfkuJbnlYznp5HmioBBMTDvvIhRTDE4NiArIFFMMTg077yJIiwgIuWfuua6luaXpSI6ICI3LzI544CBNy8zMCIsICLpoJDkvLDlhaXluLMiOiAiOC8xMCIsICLkuIvmrKHnlLPoq4vml6UiOiAiNy8yNe+8iFQrNO+8iSJ9fSwgImp1bHlfZGl2aWRlbmRfY2FsZW5kYXIiOiB7IuS+hua6kCI6ICLpvo3kupTlrpjmlrnphY3mga/ml6Xmm4bvvIhDb21wYW55X0xlZGdlci5tZO+8iSIsICLmkanmoLkgSlBNIjogeyLln7rmupbml6UiOiAiMDcvMDciLCAi5YKZ6Ki7IjogIuaciOWIneermem7nu+8jOW3suS6q+WPlyJ9LCAi5a6J6IGv5pS255uK5oiQ6ZW3IjogeyLln7rmupbml6UiOiAiMDcvMTQiLCAi5YKZ6Ki7IjogIuaciOS4reermem7niAx77yM56ys5LiA56uZ6L2J5YWl5qiZ55qEIn0sICJNJkcg5YWl5oGv5Z+66YeRIjogeyLln7rmupbml6UiOiAiMDcvMTciLCAi5YKZ6Ki7IjogIuaciOS4reermem7niAy77yM56ys5LqML+S4ieermei9ieWFpeaomeeahCJ9LCAi5a6J6IGvIEFJIOaUtuebiiI6IHsi5Z+65rqW5pelIjogIjA3LzI5IiwgIuWCmeiouyI6ICLmnIjlupXnq5npu54gMe+8jOesrOWbm+ermei9ieWFpeaomeeahCJ9LCAi6LKd6JCK5b63IEExMCI6IHsi5Z+65rqW5pelIjogIjA3LzMwIiwgIuWCmeiouyI6ICLmnIjlupXnq5npu54gMu+8jOesrOWbm+ermei9ieWFpeaomeeahCJ9fSwgImNvbXBsZXRlZF9vcGVyYXRpb25zIjogW3siZGF0ZSI6ICIyMDI2LTA3LTA5IiwgInBvbGljeSI6ICJGSjMzIiwgIuaTjeS9nCI6ICLotJblm57ovYnnlLPos7wiLCAi6L2J5Ye6IjogIuaRqeagueWkmumHjeaUtuebiiIsICLovYnlhaUiOiAiRkw2NSDlronoga/mlLbnm4rmiJDplbciLCAi54uA5oWLIjogIuKchSDlt7LpgIHlh7oifSwgeyJkYXRlIjogIjIwMjYtMDctMDgiLCAicG9saWN5IjogIlFMMTg2MTA2OTQiLCAi5pON5L2cIjogIui0luWbnui9ieeUs+izvCIsICLovYnlh7oiOiAi5a6J6IGvQUnmlLbnm4rmiJDplbciLCAi6L2J5YWlIjogIk0mRyDlhaXmga/ln7rph5EiLCAi54uA5oWLIjogIuKchSDlt7LpgIHlh7oifSwgeyJkYXRlIjogIjIwMjYtMDctMDgiLCAicG9saWN5IjogIlFMMTg0ODgyMjQiLCAi5pON5L2cIjogIui0luWbnui9ieeUs+izvCIsICLovYnlh7oiOiAi5a6J6IGvQUnmlLbnm4rmiJDplbciLCAi6L2J5YWlIjogIk0mRyDlhaXmga/ln7rph5EiLCAi54uA5oWLIjogIuKchSDlt7LpgIHlh7oifV0sICJhbGxpYW56X2NvbWJpbmVkIjogeyJjb3N0IjogODAwMDAwMCwgImN1cnJlbnRfdmFsdWUiOiA3ODQ2NjkwLCAiY3VtdWxhdGl2ZV9kaXZpZGVuZCI6IDE2MTMyNDYsICJyb2kiOiAiKzE2LjQxJSIsICJtb250aGx5X2RpdmlkZW5kIjogNTU0NTF9LCAiZmlyc3RfZ29sZCI6IHsiY29zdCI6IDIwMDAwMDAsICJjdXJyZW50X3ZhbHVlIjogMTk4ODI4NSwgImN1bXVsYXRpdmVfZGl2aWRlbmQiOiA2Mzk4NSwgInJvaSI6ICIrMi42MSUiLCAibW9udGhseV9kaXZpZGVuZCI6IDEzNTkzfSwgInRvdGFsX21vbnRobHlfZGl2aWRlbmQiOiA2OTA0NH0sICJwYWdlNF9saXF1aWRpdHkiOiB7ImJhbmtzIjogW3sibmFtZSI6ICLmmJ/lsZXpioDooYwiLCAiYWNjb3VudCI6ICLmtLvmnJ/lhLLok4QiLCAiYmFsYW5jZSI6IDcyODcsICLmsLTkvY0iOiAi5L2O6aSY6aGNIiwgIueLgOaFiyI6ICLlu7rorbDoo5zluqsgMzBLIn0sIHsibmFtZSI6ICLnrKzkuIDpioDooYwiLCAiYWNjb3VudCI6ICJpTEVPIiwgImJhbGFuY2UiOiA1MDAwMCwgIuawtOS9jSI6ICLmraPluLgiLCAi54uA5oWLIjogIuS/neiyu+aJo+asviJ9LCB7Im5hbWUiOiAi5bCH5L6G6YqA6KGMIiwgImFjY291bnQiOiAiRGlnaXRhbCBTYXZpbmdzIiwgImJhbGFuY2UiOiAyMDAwMDAwLCAi5rC05L2NIjogIuWFheijlSIsICLni4DmhYsiOiAi5qmf5pyD5a2Q5b2I6LOH6YeRIn1dLCAiaW5mbG93cyI6IFt7Iml0ZW0iOiAi5Y+w6Zu76Jaq5rC0IiwgImFtb3VudCI6IDgyMjY1LCAiZGF0ZSI6ICI3LzYrNy84IiwgInN0YXR1cyI6ICLinIUifSwgeyJpdGVtIjogIuaIv+enn++8iOWkp+e+qeihl++8iSIsICJhbW91bnQiOiAyNDAwMCwgImRhdGUiOiAi5q+P5pyIIiwgInN0YXR1cyI6ICLij7MifSwgeyJpdGVtIjogIuWuieiBr+mFjeaBryBBK0IiLCAiYW1vdW50IjogNTU0NTEsICJkYXRlIjogIjcvOSIsICJzdGF0dXMiOiAi4pyFIn0sIHsiaXRlbSI6ICLnrKzkuIDph5HphY3mga8iLCAiYW1vdW50IjogMTM1OTMsICJkYXRlIjogIjcvOCIsICJzdGF0dXMiOiAi4pyFIn0sIHsiaXRlbSI6ICLliKnmga/mlLblhaUiLCAiYW1vdW50IjogMjg1OCwgImRhdGUiOiAi5q+P5pyIIiwgInN0YXR1cyI6ICLinIUifV0sICJwYXlhYmxlcyI6IFt7ImRhdGUiOiAiNy8xMyIsICJpdGVtIjogIuaYn+Wxlee1kOa4hSIsICJhbW91bnQiOiA0ODkzNTI5LCAicHJpb3JpdHkiOiAi8J+UtCBQMCJ9LCB7ImRhdGUiOiAiNy8yMCIsICJpdGVtIjogIua0sumam1fmiL/osrgiLCAiYW1vdW50IjogNjU3MzQsICJwcmlvcml0eSI6ICLwn5+hIFAxIn0sIHsiZGF0ZSI6ICI3LzIyIiwgIml0ZW0iOiAi546J5bGx5L+h55So5Y2hIiwgImFtb3VudCI6IDMxNzYsICJwcmlvcml0eSI6ICLwn5+iIFAyIn0sIHsiZGF0ZSI6ICI4LzEiLCAiaXRlbSI6ICLlpKfnvqnooZfmiL/osrgr5Yip5oGvIiwgImFtb3VudCI6IDMzNzI0LCAicHJpb3JpdHkiOiAi8J+foSBQMSJ9XSwgInJ1bndheV9tb250aHMiOiAyMS4xfSwgInBhZ2U1X2FjdGlvbnMiOiB7InAwIjogW3siaXRlbSI6ICLmmJ/lsZXoo5zluqsgMzBLIiwgImRlYWRsaW5lIjogIuS7iuaXpSJ9LCB7Iml0ZW0iOiAiNy8xMyDmmJ/lsZXntZDmuIXmupblgpkiLCAiZGVhZGxpbmUiOiAiNy8xMyJ9XSwgInAxIjogW3siaXRlbSI6ICIwMDUxIOiyt+WFpSIsICJxdHkiOiAiOCDlvLUiLCAiY29zdCI6ICJ+MTc2LTIyMEsiLCAidGltaW5nIjogIjcvMTMg5pif5bGV57WQ5riF5b6MIn0sIHsiaXRlbSI6ICLmiL/np5/norroqo3lhaXluLMiLCAiZGVhZGxpbmUiOiAiNy8xMS0xMiJ9LCB7Iml0ZW0iOiAi56ys5LiA56uZ57WQ566X56K66KqN77yIRkw2Ne+8iSIsICJkZWFkbGluZSI6ICI3LzEzIn0sIHsiaXRlbSI6ICLnrKzkuowv5LiJ56uZ57WQ566X56K66KqN77yITSZH77yJIiwgImRlYWRsaW5lIjogIjcvMTUifV0sICJwMiI6IFt7Iml0ZW0iOiAiMDA5ODIzLzAwOTgyNCIsICJ0aW1pbmciOiAi6KeA5a+f5LiA5YCL5pyIIn0sIHsiaXRlbSI6ICIwMDUwIOmFjeaBr+e4ruawtCIsICLpmaTmga/ml6UiOiAiNy8yMSIsICLlhaXluLPml6UiOiAiOC8xMCJ9LCB7Iml0ZW0iOiAiTSZHIOWfuua6luaXpSIsICJkYXRlIjogIjcvMTcifSwgeyJpdGVtIjogIui2hei3jC/otoXmvLLnm6PmjqciLCAidGltaW5nIjogIuavj+mAsSJ9XSwgInBhdXNlZCI6IFt7Iml0ZW0iOiAiMDA1NiIsICJyZWFzb24iOiAi55uu5YmN5oyB5pyJIDEg5by177yM5YeN57WQ5Lit77yM55+t5pyf54Sh5rOV5Yqg56K877yM562J6Kej5oq85YaN6KmV5LywIn0sIHsiaXRlbSI6ICIwMDkwM0IvMDA1MiDosrflhaUiLCAicmVhc29uIjogIuiIh+ePvuaciemDqOS9jemHjeeWiiJ9LCB7Iml0ZW0iOiAiMDA2MjA4IOWKoOeivCIsICJyZWFzb24iOiAi6LOH6YeR5LiN6Laz77yM562JIDcvMTMg5b6M6KmV5LywIn1dfSwgInJlbGF5X3N0YXR1cyI6IHsiZmlyc3RfbGVnIjogeyJkb25lIjogdHJ1ZSwgImRhdGUiOiAiMjAyNi0wNy0wOSIsICJmcm9tIjogIuaRqeagueWkmumHjeaUtuebiiIsICJ0byI6ICJGTDY1IOWuieiBr+aUtuebiuaIkOmVtyJ9LCAic2Vjb25kX2xlZyI6IHsiZG9uZSI6IHRydWUsICJkYXRlIjogIjIwMjYtMDctMDgiLCAiZnJvbSI6ICLlronoga9BSeaUtuebiuaIkOmVtyIsICJ0byI6ICJNJkcg5YWl5oGv5Z+66YeRIiwgInBvbGljeSI6ICJRTDE4NjEwNjk0In0sICJ0aGlyZF9sZWciOiB7ImRvbmUiOiB0cnVlLCAiZGF0ZSI6ICIyMDI2LTA3LTA4IiwgImZyb20iOiAi5a6J6IGvQUnmlLbnm4rmiJDplbciLCAidG8iOiAiTSZHIOWFpeaBr+WfuumHkSIsICJwb2xpY3kiOiAiUUwxODQ4ODIyNCJ9LCAiZm91cnRoX2xlZyI6IHsiZG9uZSI6IGZhbHNlLCAicGxhbm5lZCI6ICLmnIjlupUiLCAiZnJvbSI6ICJNJkcg5YWl5oGv5Z+66YeRIiwgInRvIjogIuWuieiBr0FJ5pS255uK5oiQ6ZW3ICsg6LKd6JCK5b635LiW55WM56eR5oqAQTEwIn19LCAicGFnZXMiOiB7InBhZ2UxX3dlYWx0aF9iYXNlbGluZSI6IHsiYWN0dWFsX2Nhc2hfZmxvdyI6IHsiaW5jb21lIjogeyLlj7Dpm7volqrmsLQiOiA4MjI2NSwgIuaIv+ennyI6IDI0MDAwLCAi6YWN5oGvIjogNjkwNDQsICLliKnmga8iOiAyODU4fSwgImV4cGVuc2UiOiB7IuaIv+iyuCI6IDk5NDU4LCAi5raI6LK7IjogNDAwMDAsICLmspnpub/miL/np58iOiA0NTAwfX0sICJ0b3RhbF9pbmNvbWUiOiAxNzgxNjcsICJ0b3RhbF9leHBlbnNlIjogMTQzOTU4LCAid29ya2luZ19zdXJwbHVzIjogMzQyMDksICJyZXRpcmVtZW50X3N1cnBsdXMiOiAxOTAwMH0sICJwYWdlMl9zdHJhdGVnaWNfcmlzayI6IHsi57O757Wx55uu5qiZIjogeyLlj7DogqEiOiAiMjAlIiwgIue+juiCoSI6ICIyMCUiLCAi6Ziy5a6IIjogIjMwJSIsICLlgrXliLjnj77ph5EiOiAiMjUlIiwgIuingOWvn+e3qeihnSI6ICI1JSIsICLlkIjoqIgiOiAiMTAwJSJ9LCAi5Y+w6IKh5biC5YC85Z6L5oiQ6ZW3IjogeyLmqJnnmoQiOiAiMDA1MCswMDYyMDgrMDA5ODE2IiwgIuW4guWAvCI6IDk0NjY4MCwgIuS9lOavlCI6ICI3LjIlIiwgIue8uuWPoyI6ICItMTIuOCUifSwgIue+juiCoeW4guWAvOWei+aIkOmVtyI6IHsi5qiZ55qEIjogIjAwNjQ2KzAwOTgyMy84MjQr6IGv5Y2aK+iyneiQiuW+tyIsICLluILlgLwiOiA2MDIyMDk1LCAi5L2U5q+UIjogIjQ2LjElIiwgIue8uuWPoyI6ICIrMjYuMSUifSwgIumYsuWuiOWei+mFjeaBryI6IHsi5qiZ55qEIjogIjAwNTYrMDA3MTMrMDA4NzgrMDA5ODFBKzAwOTg0QSswMDkxOSswMDkxOCvlronoga9BSeaUtuebiuaIkOmVtyIsICLluILlgLwiOiAyNTU5MDc3LCAi5L2U5q+UIjogIjE5LjYlIiwgIue8uuWPoyI6ICItMTAuNCUifSwgIuWCteWIuOWPiuePvumHkSI6IHsi5qiZ55qEIjogIumKgOihjOePvumHkStQSU1DTyvnrKzkuIDph5Er5Z+66YeRIiwgIuW4guWAvCI6IDM1NDIyODQsICLkvZTmr5QiOiAiMjcuMSUiLCAi57y65Y+jIjogIisyLjElIn0sICLntZDoq5YiOiAi5Y+w6IKh5LiN6LazLTEyLjgl77yb576O6IKh6LaF5qiZKzI2LjEl77yb6Ziy5a6I5LiN6LazLTEwLjQl77yb6Kq/5bqmPeWKoOeivOWPsOiCoTAwNTEifSwgInBhZ2UzX2luc3VyYW5jZV9yZWxheSI6IHsic3lzdGVtX3RhcmdldCI6IHsi5Y+w6IKh5biC5YC85Z6L5oiQ6ZW3IjogIjIwJSIsICLnvo7ogqHluILlgLzlnovmiJDplbciOiAiMjAlIiwgIumYsuWuiOWei+mFjeaBryI6ICIzMCUiLCAi5YK15Yi45Y+K54++6YeRIjogIjI1JSIsICLop4Dlr58v57ep6KGdIjogIjUlIiwgIuWQiOioiCI6ICIxMDAlIn0sICJjdXJyZW50IjogeyLlj7DogqHluILlgLzlnovmiJDplbciOiB7IuaomeeahCI6ICIwMDUwICsgMDA2MjA4ICsgMDA5ODE2IiwgIuW4guWAvCI6IDk0NjY4MCwgIuS9lOavlCI6ICI3LjIlIiwgIue8uuWPoyI6ICItMTIuOCUifSwgIue+juiCoeW4guWAvOWei+aIkOmVtyI6IHsi5qiZ55qEIjogIjAwNjQ2ICsgMDA5ODIzICsgMDA5ODI0ICsg6IGv5Y2a576O5ZyL5oiQ6ZW3ICsg6LKd6JCK5b635LiW55WM56eR5oqAIiwgIuW4guWAvCI6IDYwMjIwOTUsICLkvZTmr5QiOiAiNDYuMSUiLCAi57y65Y+jIjogIisyNi4xJSJ9LCAi6Ziy5a6I5Z6L6YWN5oGvIjogeyLmqJnnmoQiOiAiMDA1NiArIDAwNzEzICsgMDA4NzggKyAwMDk4MUEgKyAwMDk4NEEgKyAwMDkxOSArIDAwOTE4ICsg5a6J6IGvQUnmlLbnm4rmiJDplbciLCAi5biC5YC8IjogMjU1OTA3NywgIuS9lOavlCI6ICIxOS42JSIsICLnvLrlj6MiOiAiLTEwLjQlIn0sICLlgrXliLjlj4rnj77ph5EiOiB7IuaomeeahCI6ICLpioDooYznj77ph5EgKyBQSU1DT+aUtuebiuWinumVtyArIOesrOS4gOmHkSArIOWfuumHkSIsICLluILlgLwiOiAzNTQyMjg0LCAi5L2U5q+UIjogIjI3LjElIiwgIue8uuWPoyI6ICIrMi4xJSJ9fSwgInN1bW1hcnkiOiB7IuWPsOiCoSI6ICLlmrTph43kuI3otrMiLCAi576O6IKhIjogIuWatOmHjei2heaomSIsICLpmLLlrojphY3mga8iOiAi5LiN6LazIiwgIuiqv+W6puaWueWQkSI6ICLliqDnorzlj7DogqHvvIgwMDUx77yJ77yM5LiN5a6c5YaN5Yqg576O6IKhL+WCteWIuCJ9LCAicmVsYXlfdHJhY2tpbmciOiB7IuaciOWInSI6IHsi5oyB5pyJIjogIuaRqeagueWkmumHjeaUtuebiu+8iEZKMzPvvIkiLCAi5Z+65rqW5pelIjogIjcvMDciLCAi6aCQ5Lyw5YWl5bizIjogIjcvMTkiLCAi5LiL5qyh55Sz6KuL5pelIjogIuKAlCJ9LCAi5pyI5LitIjogeyLmjIHmnIkiOiAiTSZHIOWFpeaBr+WfuumHke+8iFFMMTg2ICsgUUwxODTvvIkiLCAi5Z+65rqW5pelIjogIjcvMTciLCAi6aCQ5Lyw5YWl5bizIjogIjcvMjkiLCAi5LiL5qyh55Sz6KuL5pelIjogIjcvMTPvvIhUKzTvvIkifSwgIuaciOW6lSI6IHsi5oyB5pyJIjogIuWuieiBr0FJ5pS255uK5oiQ6ZW3ICsg6LKd6JCK5b635LiW55WM56eR5oqAQTEw77yIUUwxODYgKyBRTDE4NO+8iSIsICLln7rmupbml6UiOiAiNy8yOeOAgTcvMzAiLCAi6aCQ5Lyw5YWl5bizIjogIjgvMTAiLCAi5LiL5qyh55Sz6KuL5pelIjogIjcvMjXvvIhUKzTvvIkifX0sICJqdWx5X2RpdmlkZW5kX2NhbGVuZGFyIjogeyLkvobmupAiOiAi6b6N5LqU5a6Y5pa56YWN5oGv5pel5puG77yIQ29tcGFueV9MZWRnZXIubWTvvIkiLCAi5pGp5qC5IEpQTSI6IHsi5Z+65rqW5pelIjogIjA3LzA3IiwgIuWCmeiouyI6ICLmnIjliJ3nq5npu57vvIzlt7Lkuqvlj5cifSwgIuWuieiBr+aUtuebiuaIkOmVtyI6IHsi5Z+65rqW5pelIjogIjA3LzE0IiwgIuWCmeiouyI6ICLmnIjkuK3nq5npu54gMe+8jOesrOS4gOermei9ieWFpeaomeeahCJ9LCAiTSZHIOWFpeaBr+WfuumHkSI6IHsi5Z+65rqW5pelIjogIjA3LzE3IiwgIuWCmeiouyI6ICLmnIjkuK3nq5npu54gMu+8jOesrOS6jC/kuInnq5novYnlhaXmqJnnmoQifSwgIuWuieiBryBBSSDmlLbnm4oiOiB7IuWfuua6luaXpSI6ICIwNy8yOSIsICLlgpnoqLsiOiAi5pyI5bqV56uZ6bueIDHvvIznrKzlm5vnq5novYnlhaXmqJnnmoQifSwgIuiyneiQiuW+tyBBMTAiOiB7IuWfuua6luaXpSI6ICIwNy8zMCIsICLlgpnoqLsiOiAi5pyI5bqV56uZ6bueIDLvvIznrKzlm5vnq5novYnlhaXmqJnnmoQifX0sICJjb21wbGV0ZWRfb3BlcmF0aW9ucyI6IFt7ImRhdGUiOiAiMjAyNi0wNy0wOSIsICJwb2xpY3kiOiAiRkozMyIsICLmk43kvZwiOiAi6LSW5Zue6L2J55Sz6LO8IiwgIui9ieWHuiI6ICLmkanmoLnlpJrph43mlLbnm4oiLCAi6L2J5YWlIjogIkZMNjUg5a6J6IGv5pS255uK5oiQ6ZW3IiwgIueLgOaFiyI6ICLinIUg5bey6YCB5Ye6In0sIHsiZGF0ZSI6ICIyMDI2LTA3LTA4IiwgInBvbGljeSI6ICJRTDE4NjEwNjk0IiwgIuaTjeS9nCI6ICLotJblm57ovYnnlLPos7wiLCAi6L2J5Ye6IjogIuWuieiBr0FJ5pS255uK5oiQ6ZW3IiwgIui9ieWFpSI6ICJNJkcg5YWl5oGv5Z+66YeRIiwgIueLgOaFiyI6ICLinIUg5bey6YCB5Ye6In0sIHsiZGF0ZSI6ICIyMDI2LTA3LTA4IiwgInBvbGljeSI6ICJRTDE4NDg4MjI0IiwgIuaTjeS9nCI6ICLotJblm57ovYnnlLPos7wiLCAi6L2J5Ye6IjogIuWuieiBr0FJ5pS255uK5oiQ6ZW3IiwgIui9ieWFpSI6ICJNJkcg5YWl5oGv5Z+66YeRIiwgIueLgOaFiyI6ICLinIUg5bey6YCB5Ye6In1dLCAiYWxsaWFuel9jb21iaW5lZCI6IHsiY29zdCI6IDgwMDAwMDAsICJjdXJyZW50X3ZhbHVlIjogNzg0NjY5MCwgImN1bXVsYXRpdmVfZGl2aWRlbmQiOiAxNjEzMjQ2LCAicm9pIjogIisxNi40MSUiLCAibW9udGhseV9kaXZpZGVuZCI6IDU1NDUxfSwgImZpcnN0X2dvbGQiOiB7ImNvc3QiOiAyMDAwMDAwLCAiY3VycmVudF92YWx1ZSI6IDE5ODgyODUsICJjdW11bGF0aXZlX2RpdmlkZW5kIjogNjM5ODUsICJyb2kiOiAiKzIuNjElIiwgIm1vbnRobHlfZGl2aWRlbmQiOiAxMzU5M30sICJ0b3RhbF9tb250aGx5X2RpdmlkZW5kIjogNjkwNDR9LCAicGFnZTRfbGlxdWlkaXR5X2JhbmtpbmciOiB7ImJhbmtzIjogW3sibmFtZSI6ICLmmJ/lsZXpioDooYwiLCAiYWNjb3VudCI6ICLmtLvmnJ/lhLLok4QiLCAiYmFsYW5jZSI6IDcyODcsICLmsLTkvY0iOiAi5L2O6aSY6aGNIiwgIueLgOaFiyI6ICLlu7rorbDoo5zluqsgMzBLIn0sIHsibmFtZSI6ICLnrKzkuIDpioDooYwiLCAiYWNjb3VudCI6ICJpTEVPIiwgImJhbGFuY2UiOiA1MDAwMCwgIuawtOS9jSI6ICLmraPluLgiLCAi54uA5oWLIjogIuS/neiyu+aJo+asviJ9LCB7Im5hbWUiOiAi5bCH5L6G6YqA6KGMIiwgImFjY291bnQiOiAiRGlnaXRhbCBTYXZpbmdzIiwgImJhbGFuY2UiOiAyMDAwMDAwLCAi5rC05L2NIjogIuWFheijlSIsICLni4DmhYsiOiAi5qmf5pyD5a2Q5b2I6LOH6YeRIn1dLCAiaW5mbG93cyI6IFt7Iml0ZW0iOiAi5Y+w6Zu76Jaq5rC0IiwgImFtb3VudCI6IDgyMjY1LCAiZGF0ZSI6ICI3LzYrNy84IiwgInN0YXR1cyI6ICLinIUifSwgeyJpdGVtIjogIuaIv+enn++8iOWkp+e+qeihl++8iSIsICJhbW91bnQiOiAyNDAwMCwgImRhdGUiOiAi5q+P5pyIIiwgInN0YXR1cyI6ICLij7MifSwgeyJpdGVtIjogIuWuieiBr+mFjeaBryBBK0IiLCAiYW1vdW50IjogNTU0NTEsICJkYXRlIjogIjcvOSIsICJzdGF0dXMiOiAi4pyFIn0sIHsiaXRlbSI6ICLnrKzkuIDph5HphY3mga8iLCAiYW1vdW50IjogMTM1OTMsICJkYXRlIjogIjcvOCIsICJzdGF0dXMiOiAi4pyFIn0sIHsiaXRlbSI6ICLliKnmga/mlLblhaUiLCAiYW1vdW50IjogMjg1OCwgImRhdGUiOiAi5q+P5pyIIiwgInN0YXR1cyI6ICLinIUifV0sICJwYXlhYmxlcyI6IFt7ImRhdGUiOiAiNy8xMyIsICJpdGVtIjogIuaYn+Wxlee1kOa4hSIsICJhbW91bnQiOiA0ODkzNTI5LCAicHJpb3JpdHkiOiAi8J+UtCBQMCJ9LCB7ImRhdGUiOiAiNy8yMCIsICJpdGVtIjogIua0sumam1fmiL/osrgiLCAiYW1vdW50IjogNjU3MzQsICJwcmlvcml0eSI6ICLwn5+hIFAxIn0sIHsiZGF0ZSI6ICI3LzIyIiwgIml0ZW0iOiAi546J5bGx5L+h55So5Y2hIiwgImFtb3VudCI6IDMxNzYsICJwcmlvcml0eSI6ICLwn5+iIFAyIn0sIHsiZGF0ZSI6ICI4LzEiLCAiaXRlbSI6ICLlpKfnvqnooZfmiL/osrgr5Yip5oGvIiwgImFtb3VudCI6IDMzNzI0LCAicHJpb3JpdHkiOiAi8J+foSBQMSJ9XX0sICJwYWdlNV90YWN0aWNhbF9vcHMiOiB7InAwIjogW3siaXRlbSI6ICLmmJ/lsZXoo5zluqsgMzBLIiwgImRlYWRsaW5lIjogIuS7iuaXpSJ9LCB7Iml0ZW0iOiAiNy8xMyDmmJ/lsZXntZDmuIXmupblgpkiLCAiZGVhZGxpbmUiOiAiNy8xMyJ9XSwgInAxIjogW3siaXRlbSI6ICIwMDUxIOiyt+WFpSIsICJxdHkiOiAiNS0xMCDlvLUiLCAiY29zdCI6ICJ+MTEwLTIyMEsiLCAidGltaW5nIjogIjcvMTMg5pif5bGV57WQ5riF5b6MIn0sIHsiaXRlbSI6ICLmiL/np5/norroqo3lhaXluLMiLCAiZGVhZGxpbmUiOiAiNy8xMS0xMiJ9LCB7Iml0ZW0iOiAi56ys5LiA56uZ57WQ566X56K66KqN77yIRkw2Ne+8iSIsICJkZWFkbGluZSI6ICI3LzEzIn0sIHsiaXRlbSI6ICLnrKzkuowv5LiJ56uZ57WQ566X56K66KqN77yITSZH77yJIiwgImRlYWRsaW5lIjogIjcvMTUifV0sICJwMiI6IFt7Iml0ZW0iOiAiMDA5ODIzLzAwOTgyNCIsICJ0aW1pbmciOiAi6KeA5a+f5LiA5YCL5pyIIn0sIHsiaXRlbSI6ICIwMDUwIOmFjeaBr+e4ruawtCIsICLpmaTmga/ml6UiOiAiNy8yMSIsICLlhaXluLPml6UiOiAiOC8xMCJ9LCB7Iml0ZW0iOiAiTSZHIOWfuua6luaXpSIsICJkYXRlIjogIjcvMTcifSwgeyJpdGVtIjogIui2hei3jC/otoXmvLLnm6PmjqciLCAidGltaW5nIjogIuavj+mAsSJ9XSwgInBhdXNlZCI6IFt7Iml0ZW0iOiAiMDA1NiIsICJyZWFzb24iOiAi55uu5YmN5oyB5pyJIDEg5by177yM5YeN57WQ5Lit77yM55+t5pyf54Sh5rOV5Yqg56K877yM562J6Kej5oq85YaN6KmV5LywIn0sIHsiaXRlbSI6ICIwMDkwM0IvMDA1MiDosrflhaUiLCAicmVhc29uIjogIuiIh+ePvuaciemDqOS9jemHjeeWiiJ9LCB7Iml0ZW0iOiAiMDA2MjA4IOWKoOeivCIsICJyZWFzb24iOiAi6LOH6YeR5LiN6Laz77yM562JIDcvMTMg5b6M6KmV5LywIn1dfX0sICJfY2FjaGVfYnVzdGVyIjogMTc4Mzc2NDQ1MSwgIm1vbmV5Ym9va19jYXNoIjogMzA3MDAwMCwgInJ1bndheV9tb250aHMiOiAyMS4xLCAiY292ZXJhZ2VfcmF0aW8iOiAyMS4xLCAiaW5zdXJhbmNlX2N1cnJlbnRfdmFsdWUiOiA5ODc2MjgyLCAiZnVuZF9tYXJrZXRfdmFsdWUiOiA4NTgzMjgsICJtb25leWJvb2tfdG90YWwiOiAzMDcxMzQzLCAiaGlnaF95aWVsZF9zYXZpbmdzX3RvdGFsIjogMjIwMDQxMCwgImNhdGhheV9yZWZpbmFuY2VfYW1vdW50IjogNTAwMDAwLCAicmVudF9tb250aGx5X2FjdHVhbCI6IDgwMTAwLCAiY2NfbW9udGhseV9hdmdfNGNhcmRzIjogMzgwMDB9"
EMBEDDED_SNAPSHOT = json.loads(base64.b64decode(EMBEDDED_SNAPSHOT_B64).decode("utf-8"))

# 1. Snapshot 載入

# ============================================================


def _normalize_snapshot(data: dict) -> dict:
    try:
        inner = data.get("snapshot")
        if isinstance(inner, dict):
            return inner
    except Exception:
        pass
    return data


def _load_embedded() -> dict:
    try:
        return _normalize_snapshot(EMBEDDED_SNAPSHOT)
    except Exception:
        return {}


@st.cache_data(ttl=60)

def _load_external() -> dict:
    """Load snapshot from GitHub raw URL (snapshot.json in repo root)"""
    url = "https://raw.githubusercontent.com/b0988321088/longjiu-dashboard-2/main/snapshot.json"
    try:
        import urllib.request
        r = urllib.request.urlopen(url, timeout=10)
        data = json.loads(r.read().decode("utf-8"))
        print("[DEPLOY CHECK] loaded external snapshot.json from GitHub")
        return data
    except Exception as e:
        print("[DEPLOY CHECK] external snapshot load failed:", e)
        return {}


def load_snapshot() -> dict:
    # Priority: external GitHub > local files > embedded fallback
    ext = _load_external()
    if ext:
        return ext

    cwd = Path(__file__).parent
    print("[DEBUG] cwd:", cwd)

    for f in sorted(list(cwd.glob("framework_snapshot_*.json")) + list(cwd.glob("framework_snapshot_*_final.json")), reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if "snapshot" in data:
                print("[DEBUG] using local snapshot key")
                return data["snapshot"]
            if "pages" in data:
                print("[DEBUG] using local pages key")
                return data
        except Exception as e:
            print("[DEBUG] load error:", e)
            continue
    print("[DEBUG] returning empty dict, will use embedded fallback")
    return {}



print("[DEPLOY CHECK] dashboard.py v5.0.8-flagship loaded")

APP_VERSION = "v5.0.8-flagship"

# Force-bust Streamlit cache before loading so Railway never serves stale empty data

try:

    import streamlit as st

    st.cache_data.clear()

except Exception:

    pass

def _load_embedded_fallback() -> dict:
    try:
        raw = EMBEDDED_SNAPSHOT
    except Exception:
        return {}
    try:
        inner = raw.get("snapshot")
        return inner if isinstance(inner, dict) else raw
    except Exception:
        return raw if isinstance(raw, dict) else {}


SNAP = load_snapshot() or _load_embedded_fallback()

FILE_DATE = SNAP.get("generated_at", "N/A")

DATE_TAG = "🔄 " + FILE_DATE.split(" ")[0] if FILE_DATE != "N/A" else ""

SNAP_DATE = FILE_DATE.split(" ")[0] if FILE_DATE != "N/A" else "2026-07-20"



# ============================================================

# 2. CSS：龍九戰役風 dark theme + responsive

# ============================================================

def inject_css() -> None:

    st.markdown(

        """

<style>

    /* ============================================================
       龍九旗艦版 UI — Comptroller Dark Cockpit
       ============================================================ */

    /* Global dark mode force */
    html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stVerticalBlock"], [data-testid="stHorizontalBlock"] {background:#0F172A !important; color:#E2E8F0 !important; font-family:"Microsoft JhengHei","PingFang SC",sans-serif !important;}

    /* Streamlit top header / toolbar */
    header[data-testid="stHeader"], [data-testid="stToolbar"], header[data-testid="stHeader"] *, [data-testid="stToolbar"] * {background:#0F172A !important; color:#E2E8F0 !important;}

    /* Sidebar */
    [data-testid="stSidebar"] {background:#090d16 !important; color:#ffffff !important; border-right:1px solid #1e293b !important;}
    [data-testid="stSidebar"] *, [data-testid="stSidebar"] *::after, [data-testid="stSidebar"] *::before {color:#ffffff !important;}

    /* Buttons */
    .stButton>button {color:#ffffff !important; background:#1e293b !important; border:1px solid rgba(255,255,255,.2) !important; border-radius:8px !important;}
    .stButton>button[type="primary"] {background:#2563eb !important; border-color:#3b82f6 !important;}
    .stButton>button[type="secondary"] {background:#334155 !important; color:#ffffff !important;}

    /* Luxury Cards */
    .luxury-card {
        background: rgba(30,41,59,0.7);
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255,255,255,0.05);
        box-shadow: 0 10px 25px -5px rgba(0,0,0,0.3);
        border-radius: 16px;
        padding: 20px;
        margin-bottom: 16px;
        transition: all 0.3s ease;
    }
    .luxury-card:hover {
        border-color: rgba(59,130,246,0.3);
        box-shadow: 0 15px 30px -5px rgba(59,130,246,0.15);
    }

    /* Metric Cards */
    .metric-card {
        background-color: #1E293B;
        border-left: 5px solid #38BDF8;
        padding: 20px;
        border-radius: 12px;
        box-shadow: 0 4px 6px -1px rgba(0,0,0,0.15);
        margin-bottom: 16px;
    }
    .alert-card {
        background-color: #3F1D1D;
        border-left: 5px solid #F87171;
        padding: 18px;
        border-radius: 12px;
        margin-bottom: 16px;
    }
    .success-card {
        background-color: #14532D;
        border-left: 5px solid #4ADE80;
        padding: 18px;
        border-radius: 12px;
        margin-bottom: 16px;
    }

    /* KPI gradient boxes */
    .kpi-box {border-radius:12px; padding:14px 18px; color:#fff; margin:6px 0;}
    .kpi-green {background:linear-gradient(135deg,#059669,#047857);}
    .kpi-yellow{background:linear-gradient(135deg,#d97706,#b45309);}
    .kpi-red   {background:linear-gradient(135deg,#dc2626,#b91c1c);}
    .kpi-blue  {background:linear-gradient(135deg,#2563eb,#1d4ed8);}
    .kpi-purple{background:linear-gradient(135deg,#7c3aed,#6d28d9);}
    .kpi-label {font-size:0.78rem; opacity:.95; text-transform:uppercase; letter-spacing:1px; color:#0f172a !important;}
    .kpi-value {font-size:1.6rem; font-weight:700; margin-top:2px; color:#0f172a !important;}

    /* Alert banners */
    .alert {border-radius:8px; padding:10px 14px; margin:8px 0; font-size:0.92rem;}
    .alert-red    {background:#7f1d1d44; border-left:4px solid #ef4444;}
    .alert-yellow {background:#78350f44; border-left:4px solid #f59e0b;}
    .alert-green  {background:#064e3b44; border-left:4px solid #10b981;}

    /* Tables */
    table {width:100%; border-collapse:collapse;}
    th {text-align:left; padding:8px; border-bottom:1px solid #334155; color:#94a3b8; font-size:0.82rem;}
    td {padding:8px; border-bottom:1px solid #1e293b; font-size:0.9rem;}
    tr:hover td {background:#1e293b;}

    /* Morning cashflow block */
    .morning-cf {background:#0f172acc; border:1px solid #334155; border-radius:10px; padding:18px;}
    .morning-cf h3 {margin-top:0; font-size:1.05rem;}

    /* Typography */
    h1,h2,h3,h4,h5,[data-testid="stMarkdownContainer"] h1, [data-testid="stMarkdownContainer"] h2, [data-testid="stMarkdownContainer"] h3 {color:#ffffff !important;}
    .stMarkdown, .stText, .stCaption, p, span, div, label, [data-testid="stMarkdownContainer"] {color:#f1f5f9 !important;}

    /* Mobile */
    @media (max-width: 780px) {
        .kpi-value {font-size:1.2rem;}
        table {font-size:0.82rem;}
        .luxury-card {padding:14px;}
    }

    /* Tabs polish */
    .stTabs [data-baseweb="tab"] { color:#94A3B8 !important; font-size:16px !important; }
    .stTabs [data-baseweb="tab"][aria-selected="true"] { color:#38BDF8 !important; font-weight:bold !important; }

    .block-container{padding-top:1.5rem !important; padding-bottom:2rem !important;}

</style>

""",

        unsafe_allow_html=True,

    )


inject_css()


# ============================================================
# 3. 頁面選擇（Sidebar 桌面 / 按鈕 手機；單一 source of truth）
# ============================================================

# ============================================================

_PAGE_OPTS = [

    "1｜財富生命線",

    "2｜戰略異常中心",

    "3｜保單接力引擎",

    "4｜流動性調度",

    "5｜戰術任務",

]

_PAGE_ICONS = ["💰", "🛡️", "🛡️", "🏦", "📋"]



if "page" not in st.session_state:

    st.session_state.page = _PAGE_OPTS[0]



current_idx = _PAGE_OPTS.index(st.session_state.page) if st.session_state.page in _PAGE_OPTS else 0

sidebar_pick = st.sidebar.radio(

    "分頁導航",

    _PAGE_OPTS,

    index=current_idx,

    label_visibility="collapsed",

)

if sidebar_pick != st.session_state.page:

    st.session_state.page = sidebar_pick

    st.rerun()



# 手機版水平按鈕（不與 sidebar 重複 radio）

st.markdown('<div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px;">', unsafe_allow_html=True)

new_page = st.session_state.page

for i, (opt, icon) in enumerate(zip(_PAGE_OPTS, _PAGE_ICONS)):

    active = (opt == st.session_state.page)

    if st.button(f"{icon} {opt.split('｜')[-1]}", key=f"mob_pg_{i}", type="primary" if active else "secondary", use_container_width=True):

        new_page = opt

st.markdown("</div>", unsafe_allow_html=True)

if new_page != st.session_state.page:

    st.session_state.page = new_page

    st.rerun()



page = st.session_state.page



# ============================================================

# 4. 共用小工具

# ============================================================

PAGES = SNAP.get("pages", {})



page1 = SNAP.get("page1", {}) or PAGES.get("page1_wealth_baseline", {})

page3 = PAGES.get("page3_insurance_relay", {}) or PAGES.get("page3_allocation", {})

# Source priority: top-level snapshot keys first, pages.* second
page4 = SNAP.get("page4_liquidity", {}) or PAGES.get("page4_liquidity_banking", {}) or PAGES.get("page4_liquidity", {})
page5 = SNAP.get("page5_actions", {}) or PAGES.get("page5_tactical_ops", {}) or PAGES.get("page5_battle", {})

if page3 and not page3.get("current_value"):

    _p3a = page3.get("current", {})

    page3 = dict(page3)

    page3["current_value"] = _p3a.get("value") or _p3a.get("current_value") or 0

    page3["total_premium"] = _p3a.get("premium") or 0

    page3["monthly_dividend"] = _p3a.get("current_month_dividend") or _p3a.get("monthly_dividend") or 0

    page3["dividend_yield"] = _p3a.get("dividend_yield") or _p3a.get("yield") or 0

# Source priority: top-level snapshot keys first
page4 = SNAP.get("page4_liquidity", {}) or PAGES.get("page4_liquidity_banking", {}) or PAGES.get("page4_liquidity", {})
_p4raw = page4 if isinstance(page4, dict) else {}
_p4 = dict(_p4raw)
for _b in _p4raw.get("banks", []):
    if isinstance(_b, dict):
        _b.setdefault("type", "銀行")
_p4["accounts"] = list(_p4raw.get("banks", [])) + [x for x in _p4raw.get("insurance", []) if isinstance(x, dict)]
_exp = float(page1.get("total_expense", 141958) or 141958)
_tot_cash = sum(b.get("balance", 0) for b in _p4raw.get("banks", []) if isinstance(b, dict))
_p4["liquidity"] = {
    "runway_months": round(_tot_cash / _exp, 1) if _exp > 0 else 0.0,
    "three_month_buffer_twd": round(_exp * 3, 0),
    "buffer_coverage_x": round(_tot_cash / (_exp * 3), 1) if _exp > 0 else 0,
}
_p4["upcoming_outflows"] = list(_p4raw.get("payables", []))
_p4["refill_alert"] = None
page4 = _p4

page5 = SNAP.get("page5_actions", {}) or PAGES.get("page5_tactical_ops", {}) or PAGES.get("page5_battle", {})
_p5 = dict(page5) if isinstance(page5, dict) else {}
_p5["p0_tasks"] = list(_p5.get("p0", []))
page5 = _p5



# Page2：snapshot 使用不同欄位名，先別名對應
_p2 = dict(PAGES.get("page2_strategic_risk", {}))

# page2_allocation 扁平表 → allocation_analysis + concentration
if "allocation_check" not in _p2:
    _target_map = _p2.get("系統目標", {})
    _asset_keys = [_k for _k in ["台股市值型成長", "美股市值型成長", "防守型配息", "債券及現金", "觀察緩衝"] if _k in _p2]
    _current_map = {}
    for _k in _asset_keys:
        _v = _p2[_k]
        if isinstance(_v, dict):
            _current_map[_k] = float(str(_v.get("佔比", "0%")).replace("%", "").strip() or 0)
        else:
            _current_map[_k] = 0
    _target_n = {k: float(str(v).replace("%", "").strip() or 0) for k, v in _target_map.items() if isinstance(v, str)}
    _variance = {k: _current_map.get(k, 0) - _target_n.get(k, 0) for k in _target_n}
    _concentration = []
    for _k in _asset_keys:
        _v = _p2[_k]
        if isinstance(_v, dict):
            _concentration.append({
                "sector": _k,
                "target_pct": _target_n.get(_k, 0),
                "actual_pct": _current_map.get(_k, 0),
                "variance": _variance.get(_k, 0),
            })
    _p2["allocation_analysis"] = {
        "current": _current_map,
        "target": _target_n,
        "variance": _variance,
        "status": _p2.get("結論", ""),
    }
    if _concentration:
        _p2["concentration"] = _concentration
    if _p2.get("結論"):
        _p2["buffett_decision"] = {"summary": _p2["結論"], "action": _p2["結論"]}

if "industry_exposure" in _p2 and "concentration" not in _p2:

    ac = _p2["allocation_check"]

    _p2["allocation_analysis"] = {

        "current": ac.get("current", {}),

        "target": ac.get("target", {}),

        "variance": {k: ac.get("current", {}).get(k, 0) - ac.get("target", {}).get(k, 0) for k in ac.get("target", {})},

        "status": ac.get("status", ""),

    }

if "industry_exposure" in _p2 and "concentration" not in _p2:

    _p2["concentration"] = _p2["industry_exposure"]

if "buffett_view" in _p2 and "buffett_decision" not in _p2:

    _p2["buffett_decision"] = _p2["buffett_view"]

if "gemini_suggestion" in _p2 and "gemini_analysis" not in _p2:

    _p2["gemini_analysis"] = _p2["gemini_suggestion"]

page2 = _p2



# Page4：帳戶欄位別名

_p4 = dict(page4)

if "liquidity" not in _p4:

    _p4["liquidity"] = {}

page4 = _p4





def fmt_twd(v):

    """格式化為 TWD，None / 空字串安全處理"""

    if v is None or v == "":

        return "—"

    if isinstance(v, str):

        return v

    try:

        return f"{float(v):,.0f} TWD"

    except Exception:

        return str(v)





def kpi_card(label: str, value: str, color: str = "blue") -> None:

    # Prefer st.html(); fallback is a single metric render only
    try:
        st.html(
            f"""<div class='kpi-box kpi-{color}'>
            <div class='kpi-label'>{label}</div>
            <div class='kpi-value'>{value}</div>
            </div>"""
        )
    except Exception:
        st.metric(label, value)


def table(title: str, rows: list, cols: list) -> None:

    if not rows:

        st.info("尚無資料")

        return

    st.markdown(f"**{title}**")

    html = (

        ["<table><thead><tr>"]

        + [f"<th>{c}</th>" for c in cols]

        + ["</tr></thead><tbody>"]

    )

    for row in rows:

        html.append("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>")

    html.append("</tbody></table>")

    st.markdown("".join(html), unsafe_allow_html=True)





# ============================================================

# 5. 分頁內容

# ============================================================



## ---------- Page1 ----------

if page.startswith("1｜"):

    st.title("💰 財富生命線")

    ctx = page1.get("context", []) or []
    ctx = page1.get("context", []) or []
    # page1 key fallback must use snapshot keys directly; resolve `acf` once
    acf = page1.get("actual_cash_flow", {}) or {}
    monthly_income = page1.get("total_income")
    monthly_expense = page1.get("total_expense")
    working_surplus = page1.get("working_surplus")
    retire_surplus = page1.get("retirement_surplus")

    if monthly_income is None and acf.get("income"):
        monthly_income = sum(v for v in acf["income"].values() if isinstance(v, (int, float)))
    if monthly_expense is None and acf.get("expense"):
        monthly_expense = sum(v for v in acf["expense"].values() if isinstance(v, (int, float)))
    if working_surplus is None and monthly_income is not None and monthly_expense is not None:
        working_surplus = monthly_income - monthly_expense
    # retire_surplus trust snapshot; do NOT fallback to income-expense (that is working_surplus)

    runway_months = page1.get("runway_months", "—")
    if runway_months not in ("—", None) and runway_months == 0:
        runway_months = "—"

    # 若 snapshot 無 runway_months，退回 Moneybook / 月支出
    _fallback_total_cash = SNAP.get("moneybook_cash", 0)
    _fallback_expense = float(page1.get("total_expense", 141958) or 141958)
    if runway_months == "—" and _fallback_expense > 0:
        runway_months = _fallback_total_cash / _fallback_expense
        runway_months = round(runway_months, 1)

    debt_ratio_raw = page1.get("debt_ratio", SNAP.get("debt_ratio", page1.get("debt_ratio_pct", "—")))
    if isinstance(debt_ratio_raw, str) and debt_ratio_raw != "—":
        try:
            debt_ratio_raw = float(debt_ratio_raw.replace("%", "").strip())
        except Exception:
            debt_ratio_raw = "—"
    kpi_card(label="流動性 (月)", value="—" if runway_months == "—" else f"{float(runway_months):.1f} 月", color="green")
    kpi_card(label="工作期月盈餘", value=fmt_twd(page1.get("working_surplus") or working_surplus or 0), color="blue")
    kpi_card(label="退休後月盈餘", value=fmt_twd(page1.get("retirement_surplus") or retire_surplus or 0), color="purple")
    kpi_card(label="本月收入", value=fmt_twd(page1.get("total_income") or monthly_income or 0), color="green")
    kpi_card(label="本月支出", value=fmt_twd(page1.get("total_expense") or monthly_expense or 0), color="yellow")

    acf = page1.get("actual_cash_flow", {}) or {}
    if not acf:
        acf = {
            "income": {k: v for k, v in page1.get("income", {}).items() if isinstance(v, (int, float))},
            "expense": {k: v for k, v in page1.get("expense", {}).items() if isinstance(v, (int, float))},
        }
    ctx = page1.get("context", []) or []


    # 早上動態現金流

    st.markdown("<div class='morning-cf'>", unsafe_allow_html=True)

    st.markdown("### 🌅 資金流入流出動態（{}）".format(DATE_TAG.replace("🔄 ", "") or "2026-07-10"))

    def _totals(d):

        if isinstance(d, dict):

            return sum(v for v in d.values() if isinstance(v, (int, float)))

        return 0.0

    income = _totals(acf.get("income", {}))

    outflow = _totals(acf.get("expense", {}))

    surplus = income - outflow

    st.caption(f"📥 本月收入 {fmt_twd(income)} ｜ 📤 本月支出 {fmt_twd(outflow)} ｜ 💰 盈餘 {fmt_twd(surplus)}")



    income_items = acf.get("income", {})

    expense_items = acf.get("expense", {})

    if isinstance(income_items, dict) and income_items:

        st.markdown("### 📈 本月收入來源")

        _income_names = [k for k in income_items.keys() if k not in ("合計", "total")]

        _income_values = [income_items[k] for k in _income_names]

        fig = px.pie(

            names=_income_names,

            values=_income_values,

            hole=0.55,

            color_discrete_sequence=["#10b981", "#3b82f6", "#f59e0b", "#6366f1"],

        )

        fig.update_traces(

            textinfo="percent+label",

            hovertemplate="%{label}: %{value:,.0f} TWD<extra></extra>",

        )

        st.plotly_chart(fig, use_container_width=True, height=260)

    if isinstance(expense_items, dict) and expense_items:

        st.markdown("### 📉 本月支出組成")

        fig = px.pie(

            names=list(expense_items.keys()),

            values=list(expense_items.values()),

            hole=0.55,

            color_discrete_sequence=["#ef4444", "#f97316", "#ec4899", "#8b5cf6"],

        )

        fig.update_traces(

            textinfo="percent+label",

            hovertemplate="%{label}: %{value:,.0f} TWD<extra></extra>",

        )

        st.plotly_chart(fig, use_container_width=True)



    if acf.get("today_notes"):

        st.info(f"📌 {acf.get('today_notes')}")

    st.markdown("</div>", unsafe_allow_html=True)



    with st.expander("📋 收入明細"):

        table("", [[name, fmt_twd(val)] for name, val in acf.get("income", {}).items()], ["收入項目", "月額"])

    with st.expander("💸 支出明細"):

        table("", [[name, fmt_twd(val)] for name, val in acf.get("expense", {}).items()], ["支出項目", "月額"])

    with st.expander("市場脈動"):

        for item in ctx:

            st.write(f"• {item}")



    st.caption(DATE_TAG)



## ---------- Page2 ----------

elif page.startswith("2｜"):

    st.title("🐋 戰略異常中心")

    st.caption(DATE_TAG)



    red = page2.get("red_zone", [])

    if red:

        st.markdown("### 🚨 紅區（嚴重溢價 / 槓桿過度）")

        rows = []

        for r in red:

            if isinstance(r, dict):

                rows.append([

                    r.get("ticker", r.get("code", "")),

                    r.get("name", r.get("ticker", "")),

                    f"{r.get('return_pct', r.get('premium_pct', 0)):+.1f}%",

                    r.get("status", ""),

                    r.get("level", ""),

                ])

        table("", rows, ["代號", "名稱", "溢價/變化", "狀態", "等級"])



    alloc = page2.get("allocation_analysis", {})

    if alloc:

        st.markdown("### 📊 資產配置分析（40%台股 / 35%美股 / 25%高利活存現金及債券）")

        current = alloc.get("current", {})

        target = alloc.get("target", {})

        variance = alloc.get("variance", {})



        labels, cur_vals, tgt_vals, var_vals = [], [], [], []

        for k, v in current.items():

            labels.append(k)

            cur_vals.append(v)

            tgt_vals.append(target.get(k, 0))

            var_vals.append(variance.get(k, 0))



        if any(cur_vals):

            fig = px.bar(

                x=labels, y=[cur_vals, tgt_vals],

                labels={"x": "資產類別", "y": "配置 %"},

                color_discrete_sequence=["#3b82f6", "#10b981"],

                title="當前 vs 目標配置",

                barmode="group",

            )

            fig.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5), xaxis_tickangle=-15)

            st.plotly_chart(fig, use_container_width=True)



        if any(var_vals):

            fig2 = px.bar(

                x=labels, y=var_vals,

                labels={"x": "資產類別", "y": "偏離 %"},

                color=[abs(v) > 10 for v in var_vals],

                color_discrete_map={True: "#ef4444", False: "#f59e0b"},

                title="配置偏差（🔴 >10% / 🟡 >5%）",

            )

            fig2.add_hline(y=0, line_dash="dash", line_color="white")

            fig2.update_layout(xaxis_tickangle=-15)

            st.plotly_chart(fig2, use_container_width=True)



        if alloc.get("status"):

            st.warning(f"⚠️ {alloc.get('status')}")



    holdings = page2.get("holdings_composition", {})

    if holdings:

        st.markdown("### 🔍 穿透分析 - 資產成分")

        for asset_class, details in holdings.items():

            if isinstance(details, str):

                st.write(f"• {details}")

                continue

            name = details.get("name", asset_class)

            items = details.get("items", [])

            total = details.get("total_value", 0)

            pct = details.get("allocation_pct", 0)

            status = details.get("status", "")

            with st.expander(f"📦 {name} - {fmt_twd(total)} ({pct}%)"):

                for item in items:

                    st.write(f"  • {item}")

                if status:

                    st.caption(f"狀態：{status}")



    b = page2.get("buffett_decision", {})

    st.markdown("### 🧓 巴菲特視角")

    c1, c2 = st.columns(2)

    with c1:

        scope = b.get("scope", b.get("circle_of_competence", ""))

        if scope:

            st.success(f"✅ 能力圈：{scope}")

        moat = b.get("moat", b.get("holdings", ""))

        if moat:

            if isinstance(moat, list):

                moat = ", ".join(str(x) for x in moat)

            st.info(f"🛡️ 持有/護城河：{moat}")

    with c2:

        margin = b.get("margin_of_safety", b.get("insurance_assets", ""))

        if margin:

            if isinstance(margin, list):

                margin = ", ".join(str(x) for x in margin)

            st.warning(f"⚠️ 資產/保單：{margin}")

        action = b.get("action", "")

        if action:

            st.markdown(f"💡 **建議：{action}**")



    gemini = page2.get("gemini_analysis", "")

    if gemini:

        st.markdown("### 🤖 Gemini 投資建議（根據持倉與市場情報）")

        st.markdown(gemini)



    st.markdown("### 🔍 穿透式產業曝險")

    rows = []

    for c in page2.get("concentration", []):

        if isinstance(c, dict):

            rows.append([c.get("industry", c.get("name", "")), fmt_twd(c.get("exposure_twd", 0)), f'{float(c.get("weight_pct", 0) or 0):.1f}%'])

        else:

            rows.append([str(c), "—", "—"])

    if rows:

        table("", rows, ["產業", "實質曝險", "權重"])

    else:

        st.caption("尚無資料")



    leverage = page2.get("leverage", {})

    if leverage and isinstance(leverage, dict):

        st.markdown("### 🏦 負債結構")

        table("", [[k, fmt_twd(v)] for k, v in leverage.items()], ["指標", "金額"])



## ---------- Page3 ----------

elif page.startswith("3｜"):

    st.title("🛡️ 保單接力引擎")

    st.caption(DATE_TAG)



    # Snapshot schema: current + summary / category breakdown
    cur = page3.get("current") if isinstance(page3.get("current"), dict) else {}
    summ = page3.get("summary") if isinstance(page3.get("summary"), dict) else {}



    # 保單現值 = allianz_combined + first_gold（非 current 資產曝險）
    allianz_val = page3.get("allianz_combined", {}).get("current_value", 0) or 0
    gold_val = page3.get("first_gold", {}).get("current_value", 0) or 0
    total_value = allianz_val + gold_val

    # 加權總報酬率（硬編碼保護，值缺失直接顯示 "—"）
    allianz_roi = page3.get("allianz_combined", {}).get("roi")
    gold_roi = page3.get("first_gold", {}).get("roi")
    overall_yield = "—"
    if (
        isinstance(allianz_val, (int, float))
        and isinstance(gold_val, (int, float))
        and total_value > 0
        and allianz_roi is not None
        and gold_roi is not None
    ):
        try:
            a_roi_f = float(str(allianz_roi).replace("%", "").replace("+", "").strip())
            g_roi_f = float(str(gold_roi).replace("%", "").replace("+", "").strip())
            weighted_roi = (allianz_val * a_roi_f + gold_val * g_roi_f) / total_value
            overall_yield = f"{weighted_roi:+.2f}%"
        except Exception:
            overall_yield = "—"



    total_cost = (

        page3.get("allianz_combined", {}).get("cost", 0)

        + page3.get("first_gold", {}).get("cost", 0)

    ) or summ.get("total_cost", summ.get("cost_basis", 0))



    monthly_div = (

        page3.get("allianz_combined", {}).get("monthly_dividend", 0)

        + page3.get("first_gold", {}).get("monthly_dividend", 0)

    ) or page3.get("total_monthly_dividend", 0) or summ.get("current_month_dividend", summ.get("monthly_dividend", 0))



    st.metric("保單現值", fmt_twd(total_value))

    st.metric("總成本", fmt_twd(total_cost))

    st.metric("總報酬率", overall_yield if isinstance(overall_yield, str) and overall_yield != "—" else "—")

    st.metric("本月配息", fmt_twd(monthly_div))



    st.markdown("### ⏱️ 三站接力時間軸（T+2 / T+4 / 月底站）")

    _relay = page3.get("relay_progress") or page3.get("relay_tracking", [])

    if isinstance(_relay, dict):

        _relay = [{"station": k, **v} for k, v in _relay.items()]

    for relay in _relay:

        st.markdown(

            f"<div style='background:#1e293b;border-left:3px solid #3b82f6;padding:8px 12px;margin:6px 0;border-radius:6px;'>"

            f"<b>{relay.get('station','')}｜{relay.get('date','')}</b><br/>"

            f"📌 {relay.get('name','')} → {relay.get('convert_to','')}<br/>"

            f"🔄 狀態：{relay.get('status') or '待排程'}｜最晚期限：{relay.get('deadline') or '待確認'}<br/>"

            f"📅 除息日：{relay.get('ex_date','')}｜預計入帳：{relay.get('schedule') or '待預估'}<br/>"

            f"💡 {relay.get('action','')}</div>",

            unsafe_allow_html=True,

        )



    # 7月配息基準日

    cal = page3.get("july_dividend_calendar", {})

    if cal:

        st.markdown("### 📅 7 月配息基準日")

        rows = []

        for name, info in cal.items():

            if name == "來源":

                continue

            rows.append([name, info.get("基準日", info.get("date", "—")), info.get("備註", info.get("note", ""))])

        if rows:

            table("", rows, ["標的", "基準日", "備註"])



    # 已完成轉換紀錄

    ops = page3.get("completed_operations", [])

    if ops:

        st.markdown("### 📋 已完成轉換操作紀錄")

        rows = [[o.get("date",""), o.get("policy",""), o.get("操作",""), o.get("轉出",""), o.get("轉入",""), o.get("狀態","")] for o in ops]

        table("", rows, ["日期", "保單", "操作", "轉出標的", "轉入標的", "狀態"])



    r = page3.get("rebalancing", {})

    st.markdown("### 🎯 70/30 裁決按鈕")

    st.write(r.get("status", ""))

    c1, c2, c3 = st.columns(3)

    c1.button("✅ 執行利潤回填", use_container_width=True)

    c2.button("⏸️ 延後投入", use_container_width=True)

    c3.button("🔄 轉入其他標的", use_container_width=True)



## ---------- Page4 ----------

elif page.startswith("4｜"):

    st.title("🏦 流動性調度站")

    st.caption(DATE_TAG)



    liq = page4.get("liquidity", {})

    if liq:
        runway_val = liq.get("runway_months", "—")
        runway_display = "—" if runway_val == "—" else f"{float(runway_val):.1f}"
        st.markdown(
            f"### 📊 流動性概況<br/>"

            f"• 流動性：{runway_display} 月<br/>"

            f"• 3個月緩衝水位：{fmt_twd(liq.get('three_month_buffer_twd', 0))}<br/>"

            f"• 覆蓋倍數：{liq.get('buffer_coverage_x', 0)}x",

            unsafe_allow_html=True,
        )


    accs = page4.get("accounts", [])

    refill = page4.get("refill_alert")

    if accs:

        bank_rows, ins_rows, total_bank, total_ins = [], [], 0, 0

        for a in accs:

            if not isinstance(a, dict):

                continue

            name = a.get("name", a.get("bank", "—"))

            atype = a.get("type", "銀行").strip()

            label = f"{name} ({atype})" if atype and atype not in ("銀行", "活存") else name

            if "保單" in atype or "保險" in atype or "投資" in atype:

                ins_rows.append([label, fmt_twd(a.get("balance", 0) or 0)])

                total_ins += a.get("balance", 0) or 0

            else:

                bank_rows.append([name, fmt_twd(a.get("balance", 0) or 0)])

                total_bank += a.get("balance", 0) or 0



        # 銀行流動性水位檢查

        st.markdown("### 🏦 銀行流動水位")

        # 銀行管控規則（唯一真值，請與 Company_Ledger.md 對齊）

        bank_controls = {

            "台新Richart":      {"function": "調度中心",       "min": 100_000,  "note": "Richart 利率 1.8%，上限 100 萬"},

            "台新薪轉":         {"function": "薪轉帳戶",       "min": 50_000,   "note": "薪轉戶，約 20 萬"},

            "台新優利存":       {"function": "高利活存",       "min": 500_000,  "note": "優利存利率 1.8%，上限 100 萬"},

            "玉山銀行":         {"function": "LINE Pay 生活消費", "min": 50_000,  "note": "月扣款約 1 萬"},

            "永豐銀行":         {"function": "房貸扣款 + 一般卡", "min": 180_000, "note": "月扣款 6 萬，控 3 個月"},

            "星展銀行":         {"function": "房貸尾數",         "min": 3_300 * 3,"note": "月扣 2.3 萬房貸+1 萬利息=3.3 萬；本月結清僅放 7,000"},

            "台北富邦":         {"function": "富邦J卡 + MOMO卡",  "min": 50_000,  "note": "月消費約 8,000，控 5 萬以上"},

            "國泰世華":         {"function": "轉貸專戶",         "min": 50_000,  "note": "轉貸用途，2個月緩衝"},

            "將來銀行":         {"function": "高利活存(1.8%)",   "min": 500_000,  "note": "活存部位約 120 萬"},

            "第一銀行":         {"function": "活存(2%)",         "min": 50_000,   "note": "上限 12 萬，目前 10 萬"},

            "現金儲備":         {"function": "備用現金",         "min": 50_000,   "note": ""},

        }

        monthly_expense = page4.get('liquidity', {}).get('three_month_buffer_twd', 431_874) / 3  # 月支出



        liquidity_rows = []

        for name, balance_str in bank_rows:

            raw = str(balance_str).replace(" TWD", "").replace(",", "").replace("+", "").replace("萬", "").replace("—", "").strip()

            try:

                bal = float(raw) * (10_000 if "萬" in str(balance_str) and raw else 1)

            except Exception:

                bal = 0



            # 依银行功能决定最低要求

            if "台新" in name or "Richart" in name:

                func = "主帳戶（調度中心）"

                req = 431_874  # 3個月總支出緩衝，DASHBOARD_SPEC

            elif "玉山" in name:

                func = "LINE Pay生活消费"

                req = 328_374  # 3個月房貸+3個月LINE Pay緩衝，DASHBOARD_SPEC

            elif "永丰" in name:

                func = "房貸扣款 + 一般卡"

                req = 180_000  # 3個月房貸(99,459)+2個月消費(42,287) buffer，DASHBOARD_SPEC

            elif "富邦" in name or "台北富邦" in name:

                func = "富邦J卡 + MOMO卡消费"

                req = 80_000  # 2个月卡片消费 buffer，DASHBOARD_SPEC

            elif "星展" in name:

                func = "房貸尾數"

                req = 30_000  # 最低警示线

            elif "國泰" in name:

                func = "轉貸專戶"

                req = 287_916  # 2个月支出缓冲，DASHBOARD_SPEC

            elif "現金" in name:

                func = "現金儲備"

                req = 50_000

            else:

                func = "日常"

                req = 50_000



            coverage = bal / req if req else 0

            months_cov = bal / monthly_expense if monthly_expense else 0

            status = "✅ 充足" if coverage >= 1 else ("⚠️ 偏低" if coverage >= 0.5 else "🔴 不足")

            liquidity_rows.append([

                name, func, balance_str,

                fmt_twd(req),

                f"{float(coverage or 0):.1f}x / {float(months_cov or 0):.1f}月",

                status

            ])



        # sort by coverage ascending

        try:

            cov = float(str(r[4]).split("x")[0].strip() or 0)

        except Exception:

            cov = 0.0

        liquidity_rows.sort(key=lambda r: cov)

        table("", liquidity_rows, ["銀行", "功能", "目前餘額", "最低要求", "覆蓋", "狀態"])



        # 低餘額預警

        warns = [r for r in liquidity_rows if "🔴" in r[5]]

        if warns:

            st.markdown("### ⚠️ 低餘額預警")

            for r in warns:

                try:

                    short = round(float(str(r[4]).split("x")[0].strip() or 0), 1)

                except Exception:

                    short = 0.0

                st.error(f"**{r[0]}** 目前 {r[2]} / 要求 {r[3]} / 覆蓋 {r[4].split('x')[0].strip()}x — {r[5]}")



        # 低餘額警示

        if refill and isinstance(refill, dict):

            st.warning(f"🔔 {refill.get('low_balance_account','?')} 餘額 {fmt_twd(refill.get('balance',0))} → 建議從 {refill.get('recommended_refill_from','?')} 調度 {fmt_twd(refill.get('refill_amount',0))}（{refill.get('reason','')}）")



        # 保單 / 投資帳戶

        st.markdown("### 🛡️ 保單 / 投資帳戶")

        if ins_rows:

            table("", ins_rows, ["保單/投資", "現值"])

        else:

            st.caption("本日無保單資料")



        # 甜甜圈

        all_names = [r[0] for r in bank_rows] + ([r[0] for r in ins_rows] if ins_rows else [])

        all_vals = []

        for r in bank_rows:

            try:

                all_vals.append(float(r[1].replace(" TWD", "").replace(",", "")))

            except Exception:

                all_vals.append(0)

        for r in ins_rows:

            try:

                all_vals.append(float(r[1].replace(" TWD", "").replace(",", "")))

            except Exception:

                all_vals.append(0)

        if all_names:

            fig = px.pie(names=all_names, values=all_vals, hole=0.45, title="帳戶/保單餘額分佈")

            fig.update_traces(textinfo="percent", hovertemplate="%{label}: %{value:,.0f} TWD<extra></extra>")

            st.plotly_chart(fig, use_container_width=True)



    refill = page4.get("refill_alert", {})

    if refill:

        st.warning(

            f"🔴 低餘額警示：{refill.get('low_balance_account', refill.get('bank',''))} "

            f"{fmt_twd(refill.get('balance', 0))} → 建議補庫 {fmt_twd(refill.get('refill_amount', 0))}"

        )



    st.markdown("### 💸 近期應付（30天）")

    for p in page4.get("upcoming_outflows", []):

        if not isinstance(p, dict):

            continue

        days_left = _days_left(p.get("date", ""))

        st.markdown(f"- **{p.get('date','')}** {p.get('name', p.get('item',''))} {fmt_twd(p.get('amount', 0))}（剩餘 {days_left} 天）")



    rt = page4.get("rental_tracker", [])

    if rt:

        st.markdown("### 🏠 租金到帳監控")

        for r in rt:

            if isinstance(r, dict):

                st.write(f"• {r.get('name','')}：{fmt_twd(r.get('amount', 0))}（{_days_left(r.get('date',''))} 天）")

            else:

                st.write(f"• {r}")



## ---------- Page5 ----------

elif page.startswith("5｜"):

    st.title("🗓️ 戰術任務")

    st.caption(DATE_TAG)



    p0 = page5.get("p0_tasks", [])

    if p0:

        st.markdown("### 🚨 決戰日前表（P0）")

        for task in p0:

            if isinstance(task, dict):

                _title = task.get("title", task.get("text", task.get("item", "")))

                _deadline = task.get("deadline", "")

                _subtitle = f"（{_deadline}）" if _deadline else ""

                st.markdown(

                    f"<div style='background:#7f1d1d44;border-left:3px solid #ef4444;padding:8px 12px;margin:6px 0;border-radius:6px;'>"

                    f"{_title}{_subtitle}</div>",

                    unsafe_allow_html=True,

                )

            else:

                st.markdown(f"<div style='background:#7f1d1d44;border-left:3px solid #ef4444;padding:8px 12px;margin:6px 0;border-radius:6px;'>{task}</div>", unsafe_allow_html=True)



    lifestyle = page5.get("lifestyle", [])

    if lifestyle:

        st.markdown("### 🧳 重要行事曆")

        for item in lifestyle:

            if isinstance(item, dict):

                st.markdown(f"- **{item.get('date','')}** {item.get('item','')} （剩餘 {_days_left(item.get('date',''))} 天）")

            else:

                st.write(item)



    ps = page5.get("payment_schedule", [])

    if ps:

        st.markdown("### 💰 繳款日曆")

        if ps and isinstance(ps[0], dict):

            rows = []

            for p in ps:

                if isinstance(p, dict):

                    rows.append([

                        p.get("cycle", ""),

                        p.get("item", ""),

                        fmt_twd(p.get("amount", 0)),

                        p.get("date", ""),

                    ])

            if rows:

                table("", rows, ["週期", "項目", "金額", "扣款日"])

        else:

            table("", ps, ["週期", "項目", "金額", "扣款日"])



    if not p0 and not lifestyle and not ps:

        report_text = page5.get("report", "")

        if report_text:

            st.markdown(report_text)



    nav = page5.get("notion_nav", {})

    if nav:

        st.markdown("### 📘 Notion 戰術導航")

        for name, url in nav.items():

            st.markdown(f"- [{name}]({url})")



# ============================================================

# 6. 頁尾

# ============================================================

st.markdown("---")

st.markdown(f"📎 資料快照：{FILE_DATE}")



# force redeploy 2026-07-11 v5.0.7 pages wrapper fix
