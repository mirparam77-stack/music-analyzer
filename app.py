from datetime import datetime
import json
import os
import re
import tempfile
from matplotlib import font_manager
from matplotlib.patches import Ellipse, PathPatch
from matplotlib.path import Path
import matplotlib.pyplot as plt
from music21 import chord, converter, interval, key, midi, note, pitch, roman, stream
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="악곡분석 콘솔 v3.0",
    page_icon="🎼",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ==========================================
# 0. 한글 폰트 탐색 및 FontProperties 반환
# ==========================================
def get_korean_font_prop():
  font_paths = [
      "C:/Windows/Fonts/malgun.ttf",
      "C:/Windows/Fonts/NanumGothic.ttf",
      "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
      "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
  ]
  for fp in font_paths:
    if os.path.exists(fp):
      try:
        font_manager.fontManager.addfont(fp)
        prop = font_manager.FontProperties(fname=fp)
        plt.rcParams["font.family"] = prop.get_name()
        plt.rcParams["axes.unicode_minus"] = False
        return prop
      except Exception:
        pass

  candidates = [
      "Malgun Gothic",
      "NanumGothic",
      "AppleGothic",
      "Noto Sans CJK KR",
  ]
  available = {f.name: f.fname for f in font_manager.fontManager.ttflist}
  for name in candidates:
    if name in available:
      plt.rcParams["font.family"] = name
      plt.rcParams["axes.unicode_minus"] = False
      return font_manager.FontProperties(fname=available[name])

  plt.rcParams["axes.unicode_minus"] = False
  return font_manager.FontProperties()


KR_FONT = get_korean_font_prop()

st.markdown(
    """
<style>
    .block-container {
        padding-top: 1.1rem;
        padding-bottom: 2rem;
        padding-left: 1rem;
        padding-right: 1rem;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 6px;
        flex-wrap: wrap;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 8px 14px;
        font-size: 0.92rem;
        border-radius: 6px 6px 0 0;
    }
    .dash-card {
        padding: 14px 16px;
        border-radius: 10px;
        margin-bottom: 14px;
        line-height: 1.65;
    }
    .phrase-box {
        padding: 10px 14px;
        border-radius: 8px;
        border: 1px solid #e0e0e0;
        background-color: #ffffff;
        margin-bottom: 10px;
    }
    .checklist-box {
        padding: 12px 16px;
        border-radius: 8px;
        background-color: #FFFBEB;
        border-left: 5px solid #F59E0B;
        margin-bottom: 10px;
    }
    @media (max-width: 768px) {
        .block-container { padding-left: 0.6rem; padding-right: 0.6rem; }
        h1 { font-size: 1.45rem !important; }
    }
</style>
""",
    unsafe_allow_html=True,
)

DB_PATH = "song_database.json"


# ==========================================
# 1. song_database.json 관리 (로드 / 저장 / 삭제)
# ==========================================
def load_db():
  if not os.path.exists(DB_PATH):
    return {}
  try:
    with open(DB_PATH, "r", encoding="utf-8") as f:
      data = json.load(f)
      if isinstance(data, list):
        converted = {}
        for idx, item in enumerate(data):
          title = (
              item.get("title") or item.get("곡명") or f"보관곡_{idx+1}"
          )
          converted[title] = item
        return converted
      return data if isinstance(data, dict) else {}
  except Exception as e:
    st.sidebar.error(f"DB 로드 오류: {e}")
    return {}


def save_db(db_dict):
  with open(DB_PATH, "w", encoding="utf-8") as f:
    json.dump(db_dict, f, ensure_ascii=False, indent=2)


def upsert_song(title, payload):
  db = load_db()
  payload["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
  db[title] = payload
  save_db(db)


def delete_song(title):
  db = load_db()
  if title in db:
    del db[title]
    save_db(db)
    return True
  return False


# ==========================================
# 2. 정통 화성학 표기 변환기
# ==========================================
def format_traditional_roman(ch, rn, global_key):
  has_b6 = any(
      p.name.endswith("-") and p.name[:-1] in ["A", "E", "D", "F", "C", "G"]
      for p in ch.pitches
  )
  has_sharp4 = any("#" in p.name for p in ch.pitches)
  if has_b6 and has_sharp4 and len(ch.pitches) >= 3:
    if len(ch.pitches) == 3:
      return "It.6", "증6화음 (It.6)"
    elif any(
        iv.semitones == 6
        for i, p1 in enumerate(ch.pitches)
        for p2 in ch.pitches[i + 1 :]
        for iv in [interval.Interval(p1, p2)]
    ):
      return "Gr.6", "증6화음 (Gr.6)"
    else:
      return "Fr.6", "증6화음 (Fr.6)"

  if rn is None:
    return "경과/비화성", "비화성음 / 경과 진행"

  base_rn = rn.romanNumeralAlone or ""
  fig = rn.figure or base_rn
  common_l = (rn.commonName or "").lower()

  if (
      base_rn.upper().startswith("I")
      and len(base_rn.replace("b", "").replace("#", "")) <= 3
  ):
    func_kr = "으뜸화음 (Tonic)"
  elif base_rn.startswith("V"):
    func_kr = "딸림화음 (Dominant)"
  elif base_rn.lower().startswith("iv") or base_rn.lower().startswith("ii"):
    func_kr = "버금딸림 영역 (Subdominant)"
  elif "vii" in base_rn.lower():
    func_kr = "이끈음 화성 (Leading-Tone)"
  else:
    func_kr = "화성 진행 (Harmonic)"

  if "diminished seventh" in common_l or base_rn.startswith("vii°"):
    inv = ch.inversion()
    if len(ch.pitches) >= 4:
      sym = {0: "vii°7", 1: "vii°6/5", 2: "vii°4/3", 3: "vii°4/2"}.get(
          inv, "vii°7"
      )
    else:
      sym = "vii°6" if inv == 1 else "vii°"
    return sym, f"감7/감화음 · {func_kr}"

  if "half-diminished" in common_l or "ø" in fig:
    inv = ch.inversion()
    suffix = {0: "ø7", 1: "ø6/5", 2: "ø4/3", 3: "ø4/2"}.get(inv, "ø7")
    clean_base = base_rn.replace("ø", "").replace("7", "")
    return f"{clean_base}{suffix}", f"반감7화음 · {func_kr}"

  if rn.isSeventh():
    inv = ch.inversion()
    clean_base = base_rn.replace("7", "")
    inv_map = {0: "7", 1: "6/5", 2: "4/3", 3: "4/2"}
    return f"{clean_base}{inv_map.get(inv, '7')}", f"7화음 · {func_kr}"

  inv = ch.inversion()
  if inv == 1:
    return f"{base_rn}6", f"1전위 (6화음) · {func_kr}"
  elif inv == 2:
    return f"{base_rn}6/4", f"2전위 (6-4화음) · {func_kr}"
  else:
    return (base_rn if base_rn else fig), f"기본위치 · {func_kr}"


# ==========================================
# 3. 조성별 7음계 다이아토닉 3화음 오선 악보 및 장·단조 기능 박스
# ==========================================
def parse_key_safe(key_label):
  try:
    parts = str(key_label).strip().split()
    tonic_str = parts[0]
    mode_str = parts[1].lower() if len(parts) > 1 else "major"
    if mode_str.startswith("m") and mode_str != "major":
      return key.Key(tonic_str, "minor")
    return key.Key(tonic_str, "major")
  except Exception:
    return key.Key("C", "major")


def get_scale_7_pitches(k_obj, is_major):
  try:
    if is_major:
      sc = key.Key(k_obj.tonic, "major").getScale("major")
    else:
      sc = key.Key(k_obj.tonic, "minor").getScale("harmonic")
    pitches_list = list(sc.getPitches("C4", "B4"))
    if len(pitches_list) >= 7:
      return pitches_list[:7]
  except Exception:
    pass

  tonic_p = pitch.Pitch(f"{k_obj.tonic.name}4")
  steps = (
      [0, 2, 4, 5, 7, 9, 11] if is_major else [0, 2, 3, 5, 7, 8, 11]
  )
  return [tonic_p.transpose(s) for s in steps]


def draw_treble_clef(ax, cx=0.68, cy=70.0):
  """자연스러운 곡선의 높은음자리표(G clef)를 그립니다."""
  # G선(y=67) 주변 고리 + 부드러운 상단 루프 + 하단 갈고리
  verts = [
      (cx - 0.02, cy - 3.0),
      (cx + 0.16, cy - 3.0),
      (cx + 0.18, cy - 0.8),
      (cx - 0.14, cy - 0.5),
      (cx - 0.16, cy + 2.2),
      (cx + 0.10, cy + 4.2),
      (cx + 0.08, cy + 6.8),
      (cx + 0.02, cy + 7.4),
      (cx - 0.02, cy + 5.8),
      (cx - 0.02, cy - 5.2),
      (cx - 0.02, cy - 6.8),
      (cx - 0.15, cy - 7.2),
      (cx - 0.18, cy - 6.2),
      (cx - 0.10, cy - 5.9),
  ]
  codes = [
      Path.MOVETO,
      Path.CURVE4,
      Path.CURVE4,
      Path.CURVE4,
      Path.CURVE4,
      Path.CURVE4,
      Path.CURVE4,
      Path.CURVE4,
      Path.CURVE4,
      Path.LINETO,
      Path.CURVE4,
      Path.CURVE4,
      Path.CURVE4,
      Path.CURVE4,
  ]
  patch = PathPatch(
      Path(verts, codes),
      facecolor="none",
      edgecolor="#1f2937",
      linewidth=1.9,
      zorder=3,
  )
  ax.add_patch(patch)
  ax.scatter([cx - 0.10], [cy - 6.3], s=22, color="#1f2937", zorder=3)


def draw_key_triads_staff(key_labels):
  """각 조성(전조 포함)의 7개 음계음 위 3화음과 로마숫자·화성 기능(T/S/D)을 높은음자리표 오선 악보로 그립니다."""
  unique_keys = []
  for k in key_labels:
    if k and k not in unique_keys:
      unique_keys.append(k)
  if not unique_keys:
    unique_keys = ["C major"]

  major_info = [
      ("I", "T\n(Tonic)"),
      ("ii", "S sub.\n(Supertonic)"),
      ("iii", "T/D\n(Mediant)"),
      ("IV", "S\n(Subdominant)"),
      ("V", "D\n(Dominant)"),
      ("vi", "T\n(Submediant)"),
      ("vii°", "D\n(Leading-Tone)"),
  ]
  minor_info = [
      ("i", "t\n(Tonic)"),
      ("ii°", "S\n(Supertonic)"),
      ("III+", "t/D\n(Mediant)"),
      ("iv", "s\n(Subdominant)"),
      ("V", "D\n(Dominant)"),
      ("VI", "s\n(Submediant)"),
      ("vii°", "D\n(Leading-Tone)"),
  ]

  fig, axes = plt.subplots(
      len(unique_keys),
      1,
      figsize=(11.5, 4.5 * len(unique_keys)),
      squeeze=False,
  )
  fig.patch.set_facecolor("#FFFFFF")

  staff_x_start = 0.4
  staff_x_end = 7.6
  # 5선 간격을 모두 동일(3단위)하게 설정
  staff_lines = [64, 67, 70, 73, 76]
  ledger_above = [79, 82]
  ledger_below = [61, 58]

  for idx, k_label in enumerate(unique_keys):
    ax = axes[idx][0]
    ax.set_facecolor("#FFFDF9")
    ax.set_aspect("auto")

    k_obj = parse_key_safe(k_label)
    is_major = k_obj.mode == "major"
    scale_pitches = get_scale_7_pitches(k_obj, is_major)

    # 일정 간격 오선 5선 그리기
    for sl in staff_lines:
      ax.plot(
          [staff_x_start, staff_x_end],
          [sl, sl],
          color="#333333",
          linewidth=1.15,
          alpha=0.9,
          zorder=1,
      )

    # 높은음자리표 그리기
    draw_treble_clef(ax, cx=0.68, cy=70.0)

    degree_meta = major_info if is_major else minor_info
    for deg_idx in range(7):
      x_pos = 1.35 + deg_idx * 0.92
      root_p = scale_pitches[deg_idx]
      third_p = scale_pitches[(deg_idx + 2) % 7]
      fifth_p = scale_pitches[(deg_idx + 4) % 7]

      # 실제 화음의 음정 차이(반음 수)를 반영해 3도 쌓기 화음 모양 유지
      iv_13 = max(3, min(4, interval.Interval(root_p, third_p).semitones))
      iv_35 = max(3, min(4, interval.Interval(third_p, fifth_p).semitones))

      # 오선(61~82) 범위 내에 맞춰 3화음 세 음의 y좌표 산출
      step_y = 1.95
      p1_y = 61.0 + deg_idx * 1.45
      p2_y = p1_y + step_y * (iv_13 / 3.5)
      p3_y = p2_y + step_y * (iv_35 / 3.5)

      for note_y in (p1_y, p2_y, p3_y):
        if note_y <= 61.5:
          for lp in ledger_below:
            if note_y <= lp + 1.1:
              ax.plot(
                  [x_pos - 0.26, x_pos + 0.26],
                  [lp, lp],
                  color="#333333",
                  linewidth=1.15,
                  zorder=1,
              )
        elif note_y >= 78.5:
          for lp in ledger_above:
            if note_y >= lp - 1.1:
              ax.plot(
                  [x_pos - 0.26, x_pos + 0.26],
                  [lp, lp],
                  color="#333333",
                  linewidth=1.15,
                  zorder=1,
              )

        # 음표 세 개가 서로 살짝 맞닿아 꽉 차게 보이도록 설정
        ell = Ellipse(
            (x_pos, note_y),
            width=0.34,
            height=2.25,
            facecolor="none",
            edgecolor="#1f2937",
            linewidth=1.8,
            zorder=3,
        )
        ax.add_patch(ell)

      roman, func_label = degree_meta[deg_idx]
      ax.text(
          x_pos,
          55.8,
          roman,
          fontsize=10.5,
          fontweight="bold",
          ha="center",
          va="top",
          color="#111827",
      )
      ax.text(
          x_pos,
          51.8,
          func_label,
          fontsize=8.3,
          ha="center",
          va="top",
          color="#374151",
      )

    mode_en = "Major" if is_major else "Minor (Harmonic)"
    ax.set_title(
        f"{k_label}  —  {mode_en}  (7-Scale Diatonic Triads)",
        fontsize=11,
        fontweight="bold",
        loc="left",
        pad=10,
    )
    ax.set_xlim(0.1, 7.9)
    ax.set_ylim(43.0, 85.0)
    ax.axis("off")

  fig.subplots_adjust(hspace=0.35)
  return fig


def render_major_minor_function_box():
  """장조와 단조의 도수별 화성 기능 및 명칭 비교 박스를 렌더링합니다."""
  st.markdown(
      "#### 📘 장조 · 단조 화성 기능 비교표 (Tonic / Subdominant / Dominant)"
  )
  rows = [
      ("1도", "I (T)", "i (t)", "Tonic (으뜸음)"),
      ("2도", "ii (S 대리)", "ii° (S)", "Supertonic (윗으뜸음)"),
      ("3도", "iii (T/D)", "III+ (t/D)", "Mediant (가온음)"),
      ("4도", "IV (S)", "iv (s)", "Subdominant (버금딸림음)"),
      ("5도", "V (D)", "V (D)", "Dominant (딸림음)"),
      ("6도", "vi (T)", "VI (s)", "Submediant (버금가온음)"),
      ("7도", "vii° (D)", "vii° (D)", "Leading-Tone (이끈음)"),
  ]
  table_lines = [
      "| 도수 | 장조 (Major) | 단조 (Minor) | 화성 기능 및 명칭 |",
      "| :---: | :---: | :---: | :--- |",
  ]
  for deg, maj, min_k, desc in rows:
    table_lines.append(f"| {deg} | **{maj}** | **{min_k}** | {desc} |")
  st.markdown("\n".join(table_lines))


# ==========================================
# 4. 마디 수 오류 체크 및 보정 모듈
# ==========================================
def check_and_fix_measures(score, expected_measures=0, manual_offset=0):
  parts = (
      score.parts if len(score.parts) > 0 else score.voicesToParts().parts
  )
  raw_measures = (
      len(list(parts[0].getElementsByClass(stream.Measure))) if parts else 0
  )

  has_pickup = False
  if parts:
    m_nums = [
        m.number
        for m in parts[0].getElementsByClass(stream.Measure)
        if m.number is not None
    ]
    if 0 in m_nums:
      has_pickup = True

  effective_measures = max(0, raw_measures + manual_offset)
  error_msg = None

  if expected_measures > 0 and effective_measures != expected_measures:
    diff = effective_measures - expected_measures
    error_msg = (
        f"🚨 마디 수 오류 감지: 기대 {expected_measures}마디 / 현재"
        f" {effective_measures}마디 (차이: {diff:+d}마디, 원본 파싱:"
        f" {raw_measures}마디)"
    )

  return {
      "raw_measures": raw_measures,
      "effective_measures": effective_measures,
      "has_pickup": has_pickup,
      "error_msg": error_msg,
      "parts": parts,
  }


# ==========================================
# 5. 수직(화성) 및 전조 분석
# ==========================================
def analyze_vertical_and_modulations(score, global_key):
  rows = []
  modulations = []
  detected_keys = [global_key.name]
  chordified = score.chordify()
  prev_key_str = global_key.name

  for m in chordified.getElementsByClass(stream.Measure):
    m_num = m.number or 1
    local_key = m.analyze("key") if len(m.notes) > 0 else global_key
    local_key_str = local_key.name if local_key else global_key.name

    if local_key_str and local_key_str not in detected_keys:
      detected_keys.append(local_key_str)

    if local_key_str != prev_key_str:
      modulations.append(
          f"마디 {m_num} 부근: {prev_key_str} → {local_key_str} 조성/이탈 변화"
      )
      prev_key_str = local_key_str

    for ch in m.getElementsByClass(chord.Chord):
      if len(ch.pitches) >= 2:
        try:
          rn = roman.romanNumeralFromChord(ch, local_key or global_key)
        except Exception:
          rn = None

        trad_fig, func_desc = format_traditional_roman(
            ch, rn, local_key or global_key
        )
        rows.append({
            "마디": m_num,
            "조성": local_key_str,
            "구성음": ", ".join([p.nameWithOctave for p in ch.pitches]),
            "로마숫자 화성": trad_fig,
            "베이스음": ch.bass().nameWithOctave,
            "화성 기능": func_desc,
        })

  return pd.DataFrame(rows), modulations, detected_keys


# ==========================================
# 6. 프레이징 근거 추출 및 컬러 매핑 시각화
# ==========================================
def extract_phrases_with_reasons(score, df_vert, total_m):
  if total_m <= 0:
    return []
  parts = (
      score.parts if len(score.parts) > 0 else score.voicesToParts().parts
  )
  top_p = parts[0] if parts else None

  boundaries = {}
  for m_num in range(1, total_m + 1):
    reasons = []
    if top_p:
      m_obj = top_p.measure(m_num)
      if m_obj:
        if len(list(m_obj.getElementsByClass(note.Rest))) > 0:
          reasons.append("쉼표 출현으로 호흡 경계 형성")
        m_notes = list(m_obj.getElementsByClass(note.Note))
        if m_notes and m_notes[-1].quarterLength >= 2.0:
          reasons.append(
              f"마디 끝 음표({m_notes[-1].nameWithOctave})의 긴 음가로 호흡 이완"
          )

    if not df_vert.empty:
      sub_v = df_vert[df_vert["마디"] == m_num]
      if not sub_v.empty:
        last_r = str(sub_v.iloc[-1]["로마숫자 화성"])
        if last_r.startswith("I") or last_r.startswith("i"):
          reasons.append(f"으뜸화음({last_r}) 해결로 종지감 형성")
        elif last_r.startswith("V"):
          reasons.append(f"딸림화음({last_r}) 머무름으로 반종지/긴장 형성")

    if m_num % 4 == 0 and m_num < total_m:
      reasons.append("4마디 악구 균형점")

    if len(reasons) >= 2 or (m_num % 4 == 0 and len(reasons) >= 1):
      boundaries[m_num] = reasons

  phrases = []
  start = 1
  idx = 1
  for end_m, r_list in sorted(boundaries.items()):
    if start <= end_m <= total_m:
      phrases.append({
          "이름": f"Phrase {idx}",
          "시작": start,
          "끝": end_m,
          "근거": " / ".join(r_list),
      })
      start = end_m + 1
      idx += 1

  if start <= total_m:
    phrases.append({
        "이름": f"Phrase {idx}",
        "시작": start,
        "끝": total_m,
        "근거": "최종 종결 악구 (Final Cadence)",
    })
  return phrases


def get_color_mapping(global_key):
  is_major = global_key.mode == "major"
  if is_major:
    bg = "#FFFDF5"
    accent = "#F4A261"
    mood = f"밝고 명료한 장조 ({global_key.name})"
  else:
    bg = "#F4F5FB"
    accent = "#5C6BC0"
    mood = f"차분하고 서정적인 단조 ({global_key.name})"
  return {"mood": mood, "bg": bg, "accent": accent}


def draw_phrase_timeline_chart(phrases, total_m, cmap):
  fig, ax = plt.subplots(figsize=(11.5, 2.8))
  fig.patch.set_facecolor(cmap["bg"])
  ax.set_facecolor(cmap["bg"])

  max_m = max(total_m, 1)
  ax.set_xlim(0.5, max_m + 0.5)
  ax.set_ylim(0, 10)

  for idx, p in enumerate(phrases):
    x0, x1 = p.get("시작", 1), p.get("끝", max_m)
    if idx % 2 == 1:
      ax.axvspan(x0 - 0.4, x1 + 0.4, color=cmap["accent"], alpha=0.14)
    ax.axvline(
        x=x1 + 0.4, color="#444444", linestyle="--", linewidth=1, alpha=0.6
    )
    ax.text(
        (x0 + x1) / 2,
        5.0,
        f"{p.get('이름', f'Phrase {idx+1}')}\n({x0}~{x1}마디)",
        ha="center",
        va="center",
        fontsize=9,
        fontweight="bold",
        color="#222222",
        fontproperties=KR_FONT,
    )

  ax.set_title(
      f"프레이즈 구간 흐름 | {cmap['mood']}",
      fontsize=10.5,
      loc="left",
      fontproperties=KR_FONT,
  )
  ax.set_xlabel("마디 (Measure)", fontproperties=KR_FONT)
  ax.set_yticks([])
  ax.grid(True, axis="x", linestyle=":", alpha=0.45)
  plt.tight_layout()
  return fig


def make_midi_audio(score_obj, start_m=None, end_m=None):
  target = (
      score_obj.measures(start_m, end_m)
      if (start_m is not None and end_m is not None)
      else score_obj
  )
  mf = midi.translate.music21ObjectToMidiFile(target)
  with tempfile.NamedTemporaryFile(delete=False, suffix=".mid") as tmp:
    mf.open(tmp.name, "wb")
    mf.write()
    mf.close()
    tmp.seek(0)
    raw = tmp.read()
  os.remove(tmp.name)
  return raw


# ==========================================
# 7. 상단 제목 및 캡션 (v3.0 고정)
# ==========================================
st.title("🎼 악곡분석 콘솔 v3.0")
st.caption(
    "수직(화성 · 전조) 구조 분석 / 프레이징 근거 및 편집 / 컬러 매핑 / MIDI"
    " 구간 청취"
)

db = load_db()

# ==========================================
# 8. 사이드바 (파일 업로드, 마디 체크/보정, 보관 곡 삭제)
# ==========================================
with st.sidebar:
  st.header("📂 악보 로드 및 마디 설정")
  uploaded_file = st.file_uploader(
      "악보 파일 (.mxl, .musicxml, .xml, .mid)",
      type=["mxl", "musicxml", "xml", "mid"],
  )
  expected_measures = st.number_input(
      "기대 마디 수 (0=자동, 예: 116)", min_value=0, max_value=999, value=0
  )
  manual_offset = st.number_input(
      "마디 수 수동 보정값 (오류 수정용)", min_value=-50, max_value=50, value=0
  )

  st.divider()
  st.header("🗄️ 보관된 곡 목록")
  history_list = []
  song_labels = []
  picked_song = None
  picked_data = {}

  if db:
    if isinstance(db, dict):
      if "history" in db and isinstance(db["history"], list):
        history_list = db["history"]
        song_labels = [
            (
                f"{item.get('title', item.get('곡명', f'곡_{i+1}'))}"
                f" ({item.get('composer', '')})".strip(" ()")
            )
            for i, item in enumerate(history_list)
            if isinstance(item, dict)
        ]
      else:
        for k, v in db.items():
          if k == "last_selected_song":
            continue
          song_labels.append(str(k))
          history_list.append(v if isinstance(v, dict) else {"value": v})

    if song_labels:
      picked_song = st.selectbox("보관 곡 선택", song_labels, index=0)
      picked_idx = song_labels.index(picked_song)
      picked_data = (
          history_list[picked_idx] if picked_idx < len(history_list) else {}
      )

      if st.button("🗑️ 선택 곡 삭제", use_container_width=True):
        if delete_song(picked_song):
          st.success(f"'{picked_song}' 삭제 완료")
          st.rerun()
  else:
    st.caption("보관된 곡이 없습니다.")

# ==========================================
# 9. 메인 대시보드 실행
# ==========================================
score = None
source_title = None
total_m = 0
m_info = {
    "effective_measures": 0,
    "raw_measures": 0,
    "error_msg": None,
    "has_pickup": False,
    "parts": [],
}
cmap = {"bg": "#f4f6f9", "accent": "#4a6fa5", "mood": "기본 분석 모드"}
modulations = []
detected_keys = []
df_v = pd.DataFrame()
global_key = None
phrase_state_key = "v3_phrases_default"

if uploaded_file is not None:
  source_title = uploaded_file.name
  ext = os.path.splitext(uploaded_file.name)[1]
  with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp_in:
    tmp_in.write(uploaded_file.getbuffer())
    tmp_path = tmp_in.name
  try:
    score = converter.parse(tmp_path)
  except Exception as e:
    st.error(f"❌ 파일 파싱 실패: {e}")
  finally:
    if os.path.exists(tmp_path):
      os.remove(tmp_path)
elif isinstance(picked_data, dict) and picked_data:
  source_title = (
      picked_data.get("title")
      or picked_data.get("곡명")
      or picked_data.get("source_title")
      or picked_song
  )
  total_m = picked_data.get("total_measures", 0)
  m_info = {
      "effective_measures": total_m,
      "raw_measures": picked_data.get("raw_measures", total_m),
      "error_msg": None,
      "has_pickup": False,
      "parts": picked_data.get("parts", []),
  }
  cmap = picked_data.get(
      "cmap",
      {
          "bg": "#f4f6f9",
          "accent": "#4a6fa5",
          "mood": picked_data.get("mood", "저장된 분석 데이터"),
      },
  )
  phrase_state_key = f"v3_phrases_{source_title}"
  if phrase_state_key not in st.session_state:
    st.session_state[phrase_state_key] = picked_data.get("phrases", [])
  modulations = picked_data.get("modulations", [])

if phrase_state_key not in st.session_state:
  st.session_state[phrase_state_key] = []

if score is not None:
  m_info = check_and_fix_measures(
      score, expected_measures=expected_measures, manual_offset=manual_offset
  )
  total_m = m_info["effective_measures"]

  if m_info["error_msg"]:
    st.error(m_info["error_msg"])
    st.info(
        "💡 사이드바의 **마디 수 수동 보정값**으로 마디 수를 조정하거나 **기대 마디"
        " 수**를 수정하세요."
    )

  if m_info["has_pickup"]:
    st.warning(
        "0번 마디(못갖춘마디)가 감지되었습니다. 마디 수 및 마디 번호를 확인해"
        " 주세요."
    )

  global_key = score.analyze("key")
  df_v, modulations, detected_keys = analyze_vertical_and_modulations(
      score, global_key
  )
  cmap = get_color_mapping(global_key)

  phrase_state_key = f"v3_phrases_{source_title}"
  if phrase_state_key not in st.session_state:
    if (
        source_title in db
        and isinstance(db[source_title], dict)
        and "phrases" in db[source_title]
    ):
      st.session_state[phrase_state_key] = db[source_title]["phrases"]
    else:
      st.session_state[phrase_state_key] = extract_phrases_with_reasons(
          score, df_v, total_m
      )

# 상단 요약 카드
if score is not None or (isinstance(picked_data, dict) and picked_data):
  accent_color = cmap.get("accent", cmap.get("border", "#4a6fa5"))
  st.markdown(
      f"""
      <div class="dash-card" style="background-color:{cmap['bg']}; border-left:6px solid {accent_color};">
          <strong>🎼 곡명:</strong> {source_title} &nbsp;|&nbsp;
          <strong>🏛️ 활동 시대:</strong> 고전주의 &nbsp;|&nbsp;
          <strong>🎹 조성/분위기:</strong> {cmap['mood']}<br>
          <strong>📏 마디 수:</strong> {total_m}마디 (원본 {m_info['raw_measures']}마디, 보정 {manual_offset:+d}) &nbsp;|&nbsp;
          <strong>✂️ 프레이즈:</strong> {len(st.session_state[phrase_state_key])}개
      </div>
      """,
      unsafe_allow_html=True,
  )

# 조성/전조 감지 흐름 + 관련 조성 3화음 오선 악보 + 장/단조 기능 박스
if score is not None or (isinstance(picked_data, dict) and picked_data):
  st.subheader("🎹 조성 및 전조 감지 흐름")
  fallback_key = (
      picked_data.get("key")
      if isinstance(picked_data, dict) and picked_data.get("key")
      else "C major"
  )
  key_text = global_key.name if global_key is not None else fallback_key
  st.write(f"- **기준 조성:** {key_text}")

  related_keys = []
  if key_text:
    related_keys.append(key_text)

  key_pattern = re.compile(
      r"\b([A-G](?:#|b|-)?\s+(?:major|minor))\b", re.IGNORECASE
  )
  if modulations:
    for mod in modulations[:12]:
      st.write(f"- {mod}")
      for match in key_pattern.findall(str(mod)):
        parts = match.strip().split()
        norm_key = f"{parts[0]} {parts[1].lower()}"
        if norm_key not in related_keys:
          related_keys.append(norm_key)
  else:
    st.write("- 단일 조성 중심 진행 (큰 폭의 전조 변화 미감지)")

  if score is not None and detected_keys:
    for dk in detected_keys[:8]:
      dk_name = getattr(dk, "name", str(dk)).strip()
      if dk_name and dk_name not in related_keys:
        related_keys.append(dk_name)

  if not related_keys:
    related_keys = ["C major"]

  with st.expander(
      "🎼 조성별 7음계 다이아토닉 3화음 오선 악보 & 장·단조 화성 기능 펼쳐보기/접기",
      expanded=True,
  ):
    st.write(f"**표시 조성 목록 (전조 포함):** {', '.join(related_keys)}")
    st.pyplot(draw_key_triads_staff(related_keys))
    render_major_minor_function_box()

if score is not None:
  t1, t2, t3 = st.tabs([
      "📊 통합 대시보드",
      "🎼 수직 화성 상세",
      "🎧 MIDI 구간 재생기",
  ])

  with t1:
    st.subheader("1. 프레이즈 구간 컬러 흐름")
    if st.session_state[phrase_state_key]:
      st.pyplot(
          draw_phrase_timeline_chart(
              st.session_state[phrase_state_key], total_m, cmap
          )
      )

    st.subheader("2. 수직 화성 및 로마숫자 기능 표")
    st.dataframe(df_v, use_container_width=True, height=320)

    st.subheader("3. 프레이징 구분 근거")
    for p in st.session_state[phrase_state_key]:
      st.markdown(
          f"""
          <div class="phrase-box">
              <strong>{p.get('이름', '프레이즈')}</strong> (m.{p.get('시작', '?')} ~ m.{p.get('끝', '?')})<br>
              <span>근거: {p.get('근거', '')}</span>
          </div>
          """,
          unsafe_allow_html=True,
      )

  with t2:
    st.subheader("수직 화성 및 로마숫자 상세 표")
    st.dataframe(df_v, use_container_width=True)
    if not df_v.empty:
      st.download_button(
          "📥 수직 화성 CSV 다운로드",
          data=df_v.to_csv(index=False).encode("utf-8-sig"),
          file_name=f"{source_title}_vertical_v3.csv",
          mime="text/csv",
      )

  with t3:
    st.subheader("MIDI 전체 및 프레이즈 구간 재생")
    st.audio(make_midi_audio(score), format="audio/midi")
    for p in st.session_state[phrase_state_key]:
      if p["시작"] <= p["끝"] and total_m > 0:
        st.caption(f"{p['이름']} ({p['시작']}~{p['끝']}마디)")
        st.audio(
            make_midi_audio(score, p["시작"], p["끝"]), format="audio/midi"
        )
elif isinstance(picked_data, dict) and picked_data:
  phrases_saved = st.session_state.get(phrase_state_key, [])
  if phrases_saved:
    st.subheader("프레이징 구분 근거")
    for p in phrases_saved:
      st.markdown(
          f"""
          <div class="phrase-box">
              <strong>{p.get('이름', '프레이즈')}</strong> (m.{p.get('시작', '?')} ~ m.{p.get('끝', '?')})<br>
              <span>근거: {p.get('근거', '')}</span>
          </div>
          """,
          unsafe_allow_html=True,
      )
