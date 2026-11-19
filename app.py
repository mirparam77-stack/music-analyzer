from datetime import datetime
import json
import os
import tempfile
import matplotlib.pyplot as plt
from music21 import chord, converter, interval, midi, note, roman, stream
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="악곡분석 콘솔 v3.0",
    page_icon="🎼",
    layout="wide",
    initial_sidebar_state="expanded",
)

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
          title = item.get("title") or item.get("곡명") or f"보관곡_{idx+1}"
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
# 2. 정통 화성학 표기 변환기 (교재 스타일 반영)
# ==========================================
def format_traditional_roman(ch, rn, global_key):
  """
    music21 로마숫자 분석 결과를 정통 화성학 표기(I6, V6/5, V4/2, iiø6/5, Fr.6, It.6, Gr.6 등)로 정제합니다.
    """
  pitch_names = {p.name for p in ch.pitches}

  # 증6화음 판별 (단조/장조 맥락의 b6, 1, #4 또는 b6, 1, b3, #4 등)
  has_b6 = any(
      p.name.endswith("-") and p.name[:-1] in ["A", "E", "D", "F", "C", "G"]
      for p in ch.pitches
  )
  has_sharp4 = any("#" in p.name for p in ch.pitches)
  if has_b6 and has_sharp4 and len(ch.pitches) >= 3:
    if len(ch.pitches) == 3:
      return "It.6", "Augmented Sixth (It.6)"
    elif any(
        iv.semitones == 6 for i, p1 in enumerate(ch.pitches) for p2 in ch.pitches[i+1:] for iv in [interval.Interval(p1, p2)]
    ):
      return "Gr.6", "Augmented Sixth (Gr.6)"
    else:
      return "Fr.6", "Augmented Sixth (Fr.6)"

  if rn is None:
    return "경과/비화성", "Non-Harmonic"

  base_rn = rn.romanNumeralAlone or ""
  fig = rn.figure or base_rn

  # music21 특유의 과도한 숫자 결합(예: viio5#54, iii3#2) 정돈
  if "diminished seventh" in rn.commonName.lower() or base_rn.startswith("vii°"):
    root_sym = (
        "vii°7"
        if "7" in fig or len(ch.pitches) >= 4
        else ("vii°6" if ch.inversion() == 1 else "vii°")
    )
    if ch.inversion() == 1 and len(ch.pitches) >= 4:
      root_sym = "vii°6/5"
    elif ch.inversion() == 2 and len(ch.pitches) >= 4:
      root_sym = "vii°4/3"
    elif ch.inversion() == 3 and len(ch.pitches) >= 4:
      root_sym = "vii°4/2"
    return root_sym, "Leading-Tone Diminished"

  if "half-diminished" in rn.commonName.lower() or "ø" in fig:
    inv = ch.inversion()
    suffix = (
        "ø7"
        if inv == 0
        else ("ø6/5" if inv == 1 else ("ø4/3" if inv == 2 else "ø4/2"))
    )
    clean_base = base_rn.replace("ø", "").replace("7", "")
    return f"{clean_base}{suffix}", "Half-Diminished Seventh"

  # 7화음 전위 깔끔하게 정리
  if rn.isSeventh():
    inv = ch.inversion()
    clean_base = base_rn.replace("7", "")
    inv_map = {0: "7", 1: "6/5", 2: "4/3", 3: "4/2"}
    return f"{clean_base}{inv_map.get(inv, '7')}", "Seventh Chord"

  # 3화음 전위 깔끔하게 정리
  inv = ch.inversion()
  if inv == 1:
    return f"{base_rn}6", "First Inversion (6)"
  elif inv == 2:
    return f"{base_rn}6/4", "Second Inversion (6/4)"
  else:
    return base_rn if base_rn else fig, "Root Position"


# ==========================================
# 3. 마디 수 오류 체크 및 보정 모듈
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
        f" {effective_measures}마디 (차이: {diff:+d}마디, 원본 파싱: {raw_measures}마디)"
    )

  return {
      "raw_measures": raw_measures,
      "effective_measures": effective_measures,
      "has_pickup": has_pickup,
      "error_msg": error_msg,
      "parts": parts,
  }


# ==========================================
# 4. 다성부 분리 및 수평(대위법) / 수직(화성) 분석
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
  chordified = score.chordify()
  prev_key_str = global_key.name

  for m in chordified.getElementsByClass(stream.Measure):
    m_num = m.number or 1
    local_key = m.analyze("key") if len(m.notes) > 0 else global_key
    local_key_str = local_key.name if local_key else global_key.name

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

  return pd.DataFrame(rows), modulations


# ==========================================
# 5. 프레이징 근거 추출 및 컬러 매핑 시각화
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
  fig, ax = plt.subplots(figsize=(11, 4.2))
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

  y_hi = df_horiz["MIDI"].max() + 3 if not df_horiz.empty else 80
  y_lo = df_horiz["MIDI"].min() - 3 if not df_horiz.empty else 40
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
      ax.text(
          (x0 + x1) / 2,
          y_hi - 0.7,
          f"{p['이름']} (m.{p['시작']}-{p['끝']})",
          ha="center",
          va="top",
          fontsize=8,
          fontweight="bold",
      )

  ax.set_title(
      f"컬러 매핑: 성부 흐름 및 프레이즈 구간 | {cmap['mood']}", fontsize=10.5
  )
  ax.set_xlabel("진행 이벤트")
  ax.set_ylabel("MIDI 음고")
  ax.grid(True, linestyle=":", alpha=0.45)
  ax.legend(loc="lower right", frameon=True, facecolor="white", fontsize=8.5)
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
# 6. 상단 제목 및 캡션 (v3.0 고정)
# ==========================================
st.title("🎼 악곡분석 콘솔 v3.0")
st.caption(
    "수평(대위법) · 수직(화성) 독립 분석 / 프레이징 근거 및 편집 / 컬러 매핑 / MIDI 구간 청취"
)

db = load_db()

# ==========================================
# 7. 사이드바 (파일 업로드, 116마디 등 오류 체크/보정, 보관 곡 삭제)
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
  if db:
    song_names = list(db.keys())
    picked_song = st.selectbox("보관 곡 선택", song_names)
    col_del1, col_del2 = st.columns(2)
    with col_del1:
      if st.button("🗑️ 선택 곡 삭제", use_container_width=True):
        if delete_song(picked_song):
          st.success(f"'{picked_song}' 삭제 완료")
          st.rerun()
    with col_del2:
      st.button("📥 기록 확인", use_container_width=True)

    st.json(db[picked_song])
  else:
    st.caption("보관된 곡이 없습니다.")

# ==========================================
# 8. 메인 대시보드 실행
# ==========================================
score = None
source_title = None

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

if score is not None:
  m_info = check_and_fix_measures(
      score, expected_measures=expected_measures, manual_offset=manual_offset
  )
  total_m = m_info["effective_measures"]

  if m_info["error_msg"]:
    st.error(m_info["error_msg"])
    st.info(
        "💡 사이드바의 **마디 수 수동 보정값**으로 마디 수를 조정하거나 **기대 마디 수**를"
        " 수정하세요."
    )

  if m_info["has_pickup"]:
    st.warning(
        "0번 마디(못갖춘마디)가 감지되었습니다. 마디 수 및 마디 번호를 확인해 주세요."
    )

  global_key = score.analyze("key")
  df_h = analyze_horizontal(score)
  df_v, modulations = analyze_vertical_and_modulations(score, global_key)
  cmap = get_color_mapping(global_key, df_h)

  phrase_state_key = f"v3_phrases_{source_title}"
  if phrase_state_key not in st.session_state:
    if source_title in db and "phrases" in db[source_title]:
      st.session_state[phrase_state_key] = db[source_title]["phrases"]
    else:
      st.session_state[phrase_state_key] = extract_phrases_with_reasons(
          score, df_v, total_m
      )

  # 상단 요약 카드 (활동 시대: 고전주의)
  st.markdown(
      f"""
        <div class="dash-card" style="background-color:{cmap['bg']}; border-left:6px solid {cmap['accent']};">
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

  # 조성/전조 감지 흐름 (v2.8 계승)
  st.subheader("🎹 조성 및 전조 감지 흐름")
  st.write(f"- **기준 조성:** {global_key.name}")
  if modulations:
    for mod in modulations[:12]:
      st.write(f"- {mod}")
  else:
    st.write("- 단일 조성 중심 진행 (큰 폭의 전조 변화 미감지)")

  t1, t2, t3, t4, t5 = st.tabs([
      "📊 통합 대시보드",
      "⚖️ 대위법 · 화성 상세",
      "✂️ 프레이징 근거 · 편집",
      "🎨 컬러 매핑 시각화",
      "🎧 MIDI 구간 재생기",
  ])

  # [탭 1] 대시보드에서 핵심 요소가 모두 바로 보이도록 구성
  with t1:
    st.subheader("1. 컬러 매핑 및 성부 흐름")
    if not df_h.empty:
      st.pyplot(
          draw_color_map_chart(df_h, st.session_state[phrase_state_key], cmap)
      )

    c_left, c_right = st.columns(2)
    with c_left:
      st.subheader("2. 수평 대위법 & 다성부 분리")
      st.dataframe(df_h, use_container_width=True, height=300)
    with c_right:
      st.subheader("3. 수직 화성 상세 분석 표")
      st.dataframe(df_v, use_container_width=True, height=300)

    st.subheader("4. 프레이징 구분 근거")
    for p in st.session_state[phrase_state_key]:
      st.markdown(
          f"""
                <div class="phrase-box">
                    <strong>{p['이름']}</strong> (m.{p['시작']} ~ m.{p['끝']})<br>
                    <span>근거: {p['근거']}</span>
                </div>
                """,
          unsafe_allow_html=True,
      )

    st.subheader("5. MIDI 전체 및 구간 재생")
    st.audio(make_midi_audio(score), format="audio/midi")
    for p in st.session_state[phrase_state_key]:
      if p["시작"] <= p["끝"] and total_m > 0:
        st.caption(f"{p['이름']} ({p['시작']}~{p['끝']}마디)")
        st.audio(
            make_midi_audio(score, p["시작"], p["끝"]), format="audio/midi"
        )

    st.subheader("6. 연주 해석 체크리스트")
    st.markdown(
        """
        <div class="checklist-box">
            <strong>긴장과 해소:</strong> Dominant(V) 및 부속화음(V/V, vii° 등)에서 목표 화성으로 해결될 때의 호흡과 성부 진행을 살렸는가?
        </div>
        <div class="checklist-box">
            <strong>전조 및 프레이징 전환:</strong> 조성 변화 및 프레이즈 경계에서 음색과 아티큘레이션을 어떻게 전환할 것인가?
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.subheader("7. 분석 결과 저장 및 다운로드")
    dl1, dl2 = st.columns(2)
    dl1.download_button(
        "📥 수평 대위법 CSV 다운로드",
        data=df_h.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"{source_title}_horizontal_v3.csv",
        mime="text/csv",
    )
    dl2.download_button(
        "📥 수직 화성 CSV 다운로드",
        data=df_v.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"{source_title}_vertical_v3.csv",
        mime="text/csv",
    )

  # [탭 2] 대위법 · 화성 상세
  with t2:
    col_a, col_b = st.columns(2)
    with col_a:
      st.subheader("수평 대위법 (다성부 분리)")
      v_list = ["전체"] + (list(df_h["성부"].unique()) if not df_h.empty else [])
      sel_voice = st.selectbox("성부 선택", v_list, key="tab2_voice")
      show_h = (
          df_h
          if sel_voice == "전체" or df_h.empty
          else df_h[df_h["성부"] == sel_voice]
      )
      st.dataframe(show_h, use_container_width=True)
    with col_b:
      st.subheader("수직 화성 상세 분석 표")
      st.dataframe(df_v, use_container_width=True)

  # [탭 3] 프레이징 근거 및 사용자 편집
  with t3:
    st.subheader("프레이징 구분 근거 확인 및 마디/근거 수정")
    p_list = st.session_state[phrase_state_key]
    for i, p in enumerate(p_list):
      with st.expander(f"{p['이름']} ({p['시작']}~{p['끝']}마디)", expanded=True):
        st.write(f"**근거:** {p['근거']}")
        k1, k2, k3 = st.columns([1, 1, 3])
        ns = k1.number_input(
            "시작 마디", 1, max(1, total_m), int(p["시작"]), key=f"ns_{i}"
        )
        ne = k2.number_input(
            "끝 마디", 1, max(1, total_m), int(p["끝"]), key=f"ne_{i}"
        )
        nr = k3.text_input("구분 근거 수정", value=p["근거"], key=f"nr_{i}")
        if ns != p["시작"] or ne != p["끝"] or nr != p["근거"]:
          st.session_state[phrase_state_key][i] = {
              "이름": p["이름"],
              "시작": ns,
              "끝": ne,
              "근거": nr,
          }
          st.rerun()

    if st.button("💾 현재 분석 및 프레이징 보관소에 저장"):
      upsert_song(
          source_title,
          {
              "title": source_title,
              "era": "고전주의",
              "key": global_key.name,
              "mood": cmap["mood"],
              "total_measures": total_m,
              "phrases": st.session_state[phrase_state_key],
          },
      )
      st.success(f"'{source_title}'가 보관소에 저장되었습니다.")
      st.rerun()

  # [탭 4] 컬러 매핑 시각화
  with t4:
    st.subheader("분위기 · 성부 · 프레이징 컬러 매핑")
    if not df_h.empty:
      st.pyplot(
          draw_color_map_chart(df_h, st.session_state[phrase_state_key], cmap)
      )
    else:
      st.info("표시할 음표 데이터가 없습니다.")

  # [탭 5] MIDI 구간 재생기
  with t5:
    st.subheader("전체 및 프레이즈 구간별 MIDI 재생기")
    st.markdown("**전체 곡**")
    st.audio(make_midi_audio(score), format="audio/midi")
    st.divider()
    for p in st.session_state[phrase_state_key]:
      st.markdown(f"**{p['이름']} ({p['시작']}~{p['끝']}마디)** — {p['근거']}")
      if p["시작"] <= p["끝"] and total_m > 0:
        st.audio(
            make_midi_audio(score, p["시작"], p["끝"]), format="audio/midi"
        )
      else:
        st.error("시작 마디가 끝 마디보다 클 수 없습니다.")

else:
  st.info(
      "👈 왼쪽 사이드바에서 악보 파일을 업로드해 주세요. (활동 시대 기본값: **고전주의**)"
  )
