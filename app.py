from datetime import datetime
import json
import os
import tempfile
from matplotlib import font_manager
from matplotlib.patches import Ellipse
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


def draw_key_triads_staff(key_labels):
  """각 조성(전조 포함)의 7개 음계음 위 3화음과 로마숫자·화성 기능(T/S/D)을 오선 악보로 그립니다."""
  unique_keys = []
  for k in key_labels:
    if k and k not in unique_keys:
      unique_keys.append(k)
  if not unique_keys:
    unique_keys = ["C major"]

  major_info = [
      ("I", "T\n(Tonic)"),
      ("ii", "S 대리\n(Supertonic)"),
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
      figsize=(11.5, 3.9 * len(unique_keys)),
      squeeze=False,
  )
  fig.patch.set_facecolor("#FFFFFF")
  staff_lines = [64, 67, 71, 74, 77]

  for idx, k_label in enumerate(unique_keys):
    ax = axes[idx][0]
    ax.set_facecolor("#FFFDF9")

    k_obj = parse_key_safe(k_label)
    is_major = k_obj.mode == "major"
    scale_pitches = get_scale_7_pitches(k_obj, is_major)

    # 오선 5선 그리기
    for sl in staff_lines:
      ax.plot(
          [0.4, 7.6],
          [sl, sl],
          color="#333333",
          linewidth=1.1,
          alpha=0.85,
          zorder=1,
      )
    ax.text(
        0.55,
        70.5,
        "𝄞",
        fontsize=28,
        va="center",
        ha="center",
        color="#222222",
        zorder=2,
        fontproperties=KR_FONT,
    )

    degree_meta = major_info if is_major else minor_info
    for deg_idx in range(7):
      x_pos = 1.3 + deg_idx * 0.9
      root_p = scale_pitches[deg_idx]

      # 도·레·미·파·솔·라·시 각 음 위에 3음씩 쌓기 (1도, 3도, 5도)
      p1_m = root_p.midi
      p2_m = scale_pitches[(deg_idx + 2) % 7].midi + (
          12 if deg_idx + 2 >= 7 else 0
      )
      p3_m = scale_pitches[(deg_idx + 4) % 7].midi + (
          12 if deg_idx + 4 >= 7 else 0
      )

      while p3_m > 81:
        p1_m -= 12
        p2_m -= 12
        p3_m -= 12
      while p1_m < 60:
        p1_m += 12
        p2_m += 12
        p3_m += 12

      for note_m in (p1_m, p2_m, p3_m):
        if note_m < 64:
          ax.plot(
              [x_pos - 0.16, x_pos + 0.16],
              [61, 61],
              color="#333333",
              linewidth=1.0,
              zorder=2,
          )
        elif note_m > 77:
          ax.plot(
              [x_pos - 0.16, x_pos + 0.16],
              [80, 80],
              color="#333333",
              linewidth=1.0,
              zorder=2,
          )
        ell = Ellipse(
            (x_pos, note_m),
            width=0.25,
            height=1.35,
            facecolor="#FFFFFF",
            edgecolor="#1f2937",
            linewidth=1.7,
            zorder=3,
        )
        ax.add_patch(ell)

      ax.plot(
          [x_pos + 0.12, x_pos + 0.12],
          [p1_m, p3_m],
          color="#1f2937",
          linewidth=1.1,
          zorder=3,
      )

      roman, func_label = degree_meta[deg_idx]
      ax.text(
          x_pos,
          56.5,
          roman,
          fontsize=10.5,
          fontweight="bold",
          ha="center",
          va="top",
          color="#111827",
          fontproperties=KR_FONT,
      )
      ax.text(
          x_pos,
          52.5,
          func_label,
          fontsize=8.3,
          ha="center",
          va="top",
          color="#374151",
          fontproperties=KR_FONT,
      )

    mode_kor = "장조 (Major)" if is_major else "단조 · 화성단음계 (Minor)"
    ax.set_title(
        f"{k_label}  —  {mode_kor}  (7음계 음 위 다이아토닉 3화음)",
        fontsize=11,
        fontweight="bold",
        loc="left",
        pad=10,
        fontproperties=KR_FONT,
    )
    ax.set_xlim(0.1, 7.9)
    ax.set_ylim(44.0, 84.0)
    ax.axis("off")

  plt.tight_layout()
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
# 5. 다성부 분리 및 수평(대위법) / 수직(화성) 분석
# ==========================================
def separate_voices(score):
  if len(score.parts) > 1:
    return list(score.parts)
  if score.parts:
    voices = score.parts[0].flatten().getElementsByClass(stream.Voice)
    if len(voices) > 1:
      return list(score.voicesToParts().parts)
  return list(score.parts)


def analyze_horizontal(score):
  rows = []
  parts = separate_voices(score)
  n_parts = len(parts)

  for idx, part in enumerate(parts):
    if part.partName:
      v_name = part.partName
    elif n_parts == 1:
      v_name = "통합 성부 (Voice 1)"
    elif idx == 0:
      v_name = "상성부 (Soprano)"
    elif idx == n_parts - 1:
      v_name = "저성부 (Bass)"
    else:
      v_name = f"내성부 (Inner {idx})"

    els = [
        e
        for e in part.flatten().notes
        if isinstance(e, (note.Note, chord.Chord))
    ]
    for i in range(len(els) - 1):
      c_el, n_el = els[i], els[i + 1]
      c_note = (
          c_el
          if c_el.isNote
          else (
              c_el.sortAscending()[0]
              if idx == n_parts - 1 and n_parts > 1
              else c_el.sortAscending()[-1]
          )
      )
      n_note = (
          n_el
          if n_el.isNote
          else (
              n_el.sortAscending()[0]
              if idx == n_parts - 1 and n_parts > 1
              else n_el.sortAscending()[-1]
          )
      )

      iv = interval.Interval(c_note, n_note)
      semi = abs(iv.semitones)
      if semi == 0:
        m_type = "동음 유지 (Static)"
      elif semi <= 2:
        m_type = "순차 진행 (Step)"
      else:
        m_type = "도약 진행 (Leap)"

      rows.append({
          "마디": c_el.measureNumber or 1,
          "성부": v_name,
          "현재음": c_note.nameWithOctave,
          "다음음": n_note.nameWithOctave,
          "음정": iv.directedName,
          "진행": m_type,
          "MIDI": c_note.pitch.midi,
      })
  return pd.DataFrame(rows)


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
  parts = separate_voices(score)
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


def get_color_mapping(global_key, df_horiz):
  avg_midi = df_horiz["MIDI"].mean() if not df_horiz.empty else 62
  is_major = global_key.mode == "major"
  if is_major:
    bg = "#FFFDF5" if avg_midi >= 64 else "#F7FBF2"
    accent = "#F4A261"
    v_cols = ["#E76F51", "#2A9D8F", "#457B9D", "#9B5DE5"]
    mood = f"밝고 명료한 장조 ({global_key.name})"
  else:
    bg = "#F4F5FB" if avg_midi >= 64 else "#EEF2F6"
    accent = "#5C6BC0"
    v_cols = ["#5E60CE", "#0096C7", "#C9184A", "#2B9348"]
    mood = f"차분하고 서정적인 단조 ({global_key.name})"
  return {"mood": mood, "bg": bg, "accent": accent, "voice_colors": v_cols}


def draw_color_map_chart(df_horiz, phrases, cmap):
  fig, ax = plt.subplots(figsize=(11.8, 4.8))
  fig.patch.set_facecolor(cmap["bg"])
  ax.set_facecolor(cmap["bg"])

  for i, v in enumerate(df_horiz["성부"].unique()):
    sub = df_horiz[df_horiz["성부"] == v]
    ax.plot(
        sub.index,
        sub["MIDI"],
        marker="o",
        markersize=3.5,
        linewidth=1.8,
        label=v,
        color=cmap["voice_colors"][i % len(cmap["voice_colors"])],
        alpha=0.9,
    )

  max_idx = int(df_horiz.index.max()) if not df_horiz.empty else 10
  y_hi = df_horiz["MIDI"].max() + 5.5 if not df_horiz.empty else 82
  y_lo = df_horiz["MIDI"].min() - 3.5 if not df_horiz.empty else 38
  ax.set_xlim(-5, max_idx + 18)
  ax.set_ylim(y_lo, y_hi)

  for idx, p in enumerate(phrases):
    p_sub = df_horiz[
        (df_horiz["마디"] >= p["시작"]) & (df_horiz["마디"] <= p["끝"])
    ]
    if not p_sub.empty:
      x0, x1 = p_sub.index.min(), p_sub.index.max()
      if idx % 2 == 1:
        ax.axvspan(x0, x1, color=cmap["accent"], alpha=0.10)
      ax.axvline(x=x1, color="#444444", linestyle="--", linewidth=1, alpha=0.6)
      y_pos = y_hi - 0.7 if idx % 2 == 0 else y_hi - 2.6
      x_mid = min((x0 + x1) / 2, max_idx - 8)
      ax.text(
          x_mid,
          y_pos,
          f"P{idx+1}({p['시작']}-{p['끝']})",
          ha="center",
          va="top",
          fontsize=7.8,
          fontweight="bold",
          color="#222222",
          fontproperties=KR_FONT,
      )

  ax.set_title(
      f"컬러 매핑: 성부 흐름 및 프레이즈 구간 | {cmap['mood']}",
      fontsize=10.5,
      fontproperties=KR_FONT,
  )
  ax.set_xlabel("진행 이벤트", fontproperties=KR_FONT)
  ax.set_ylabel("MIDI 음고", fontproperties=KR_FONT)
  ax.grid(True, linestyle=":", alpha=0.45)
  ax.legend(
      loc="lower right",
      frameon=True,
      facecolor="white",
      fontsize=8.5,
      prop=KR_FONT,
  )
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
    "수평(대위법) · 수직(화성) 독립 분석 / 프레이징 근거 및 편집 / 컬러 매핑 /"
    " MIDI 구간 청취"
)

db = load_db()

# ==========================================
# 8. 사이드바 (파일 업로드, 116마디 등 오류 체크/보정, 보관 곡 삭제 및 요약)
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
      picked_data = history_list[picked_idx] if picked_idx < len(history_list) else {}

      col_del1, col_del2 = st.columns(2)
      with col_del1:
        if st.button("🗑️ 선택 곡 삭제", use_container_width=True):
          if delete_song(picked_song):
            st.success(f"'{picked_song}' 삭제 완료")
            st.rerun()
      with col_del2:
        st.write("")

      if isinstance(picked_data, dict):
        st.write(f"**항목 키:** `{picked_song}`")
        if "title" in picked_data:
          st.write(f"**곡명:** {picked_data.get('title')}")
        if "composer" in picked_data:
          st.write(f"**작곡가:** {picked_data.get('composer')}")
        if "era" in picked_data:
          st.write(f"**시대:** {picked_data.get('era')}")
        if "total_measures" in picked_data:
          st.write(f"**마디 수:** {picked_data.get('total_measures')}")
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
          "border": "#4a6fa5",
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
  df_h = analyze_horizontal(score)
  df_v, modulations, detected_keys = analyze_vertical_and_modulations(
      score, global_key
  )
  cmap = get_color_mapping(global_key, df_h)

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
          <strong>🎭 분리 성부:</strong> {len(m_info['parts'])}개 &nbsp;|&nbsp;
          <strong>✂️ 프레이즈:</strong> {len(st.session_state[phrase_state_key])}개
      </div>
      """,
      unsafe_allow_html=True,
  )

# 조성/전조 감지 흐름 + 관련 조성 7화음 오선 악보 + 장/단조 기능 박스
if score is not None or (isinstance(picked_data, dict) and picked_data):
  st.subheader("🎹 조성 및 전조 감지 흐름")
  fallback_key = (
      picked_data.get("key")
      if isinstance(picked_data, dict) and picked_data.get("key")
      else globals().get("base_key_label", "C major")
  )
  key_text = global_key.name if score is not None else fallback_key
  st.write(f"- **기준 조성:** {key_text}")

  related_keys = []
  if key_text and key_text != "저장된 분석 기준":
    related_keys.append(key_text)

  if modulations:
    for mod in modulations[:12]:
      st.write(f"- {mod}")
      mod_str = str(mod)
      for token in mod_str.replace("→", " ").replace("->", " ").split():
        clean_tok = token.strip(",:;()")
        if clean_tok.lower() in {
            "major",
            "minor",
            "c",
            "d",
            "e",
            "f",
            "g",
            "a",
            "b",
            "c#",
            "d#",
            "f#",
            "g#",
            "db",
            "eb",
            "gb",
            "ab",
            "bb",
        }:
          if clean_tok not in related_keys:
            related_keys.append(clean_tok)
  else:
    st.write("- 단일 조성 중심 진행 (큰 폭의 전조 변화 미감지)")

  if score is not None and detected_keys:
    for dk in detected_keys[:8]:
      dk_name = getattr(dk, "name", str(dk))
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
  t1, t2, t3, t4, t5 = st.tabs([
      "📊 통합 대시보드",
      "⚖️ 대위법 · 화성 상세",
      "✂️ 프레이징 근거 · 편집",
      "🎨 컬러 매핑 시각화",
      "🎧 MIDI 구간 재생기",
  ])

  with t1:
    st.subheader("1. 컬러 매핑 및 성분 흐름")
    if not df_h.empty:
      st.pyplot(
          draw_color_map_chart(df_h, st.session_state[phrase_state_key], cmap)
      )

    c_left, c_right = st.columns(2)
    with c_left:
      st.subheader("2. 수평 대위법 & 다성부 분리")
      st.dataframe(df_h, use_container_width=True, height=300)
    with c_right:
      st.subheader("3. 수직 화성 및 로마숫자 기능 표")
      st.dataframe(df_v, use_container_width=True, height=300)

    st.subheader("4. 프레이징 구분 근거")
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
    col_a, col_b = st.columns(2)
    with col_a:
      st.subheader("수평 대위법 (다성부 분리)")
      v_list = ["전체"] + (
          list(df_h["성부"].unique()) if not df_h.empty else []
      )
      sel_voice = st.selectbox("성부 선택", v_list, key="tab2_voice")
      show_h = (
          df_h
          if sel_voice == "전체" or df_h.empty
          else df_h[df_h["성부"] == sel_voice]
      )
      st.dataframe(show_h, use_container_width=True)
    with col_b:
      st.subheader("수직 화성 상세")
      st.dataframe(df_v, use_container_width=True)
elif isinstance(picked_data, dict) and picked_data:
  phrases_saved = st.session_state.get(phrase_state_key, [])
  if phrases_saved:
    st.subheader("4. 프레이징 구분 근거")
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
