import base64
import json
import os
import tempfile
from music21 import chord, converter, key, roman, scale, stream
import pandas as pd
import streamlit as st

# 웹 페이지 기본 설정
st.set_page_config(
    page_title="악곡분석 프로토콜 v2.8", page_icon="🎼", layout="wide"
)

# 기본 스타일 주입
st.markdown(
    """
    <style>
    .stTable { overflow-x: auto; }
    .stButton button { width: 100%; }
    .stDownloadButton button { width: 100%; }
    [data-testid="stDataFrame"] td {
        letter-spacing: -0.5px !important;
        font-family: 'Courier New', Courier, monospace, sans-serif;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title(
    "🎼 악곡분석 콘솔 v2.8 대시보드 (오선 실선이 보이는 정통 온음표)"
)
st.markdown(
    "정통 악보 기보법을 준수하는 온음표 3화음 및 영문/백병동 화성학 체계 통합"
    " 시스템입니다."
)

# 기본 샘플 데이터 (Fernando Sor Op. 6 No. 8)
default_song_info = {
    "composer": "Fernando Sor",
    "title": "Study in C Major, Op. 6 No. 8",
    "era": "고전주의 ~ 초기 낭만주의 (1778–1839)",
    "philosophy": (
        "기타를 '작은 오케스트라'로 여기며, 성부 진행의 명료함과 고전적 균형미를"
        " 추구함."
    ),
    "measures": [
        ["C4", "E4", "G4"],
        ["G3", "D4", "F4", "B4"],
        ["C4", "E4", "G4"],
        ["F3", "A3", "C4", "F4"],
        ["G3", "B3", "D4", "G4"],
        ["C4", "E4", "G4"],
        ["A3", "C4", "E4"],
        ["D3", "F3", "A3", "C4"],
        ["G3", "B3", "D4", "G4"],
        ["C4", "E4", "G4"],
        ["G3", "D4", "F4", "B4"],
        ["C4", "E4", "G4"],
    ],
    "pdf_display": None,
}

DB_FILE = "song_database.json"


def load_db():
  if os.path.exists(DB_FILE):
    try:
      with open(DB_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        if isinstance(data, list):
          return data, ""
        elif isinstance(data, dict):
          return data.get("history", [default_song_info]), data.get(
              "last_selected", ""
          )
    except:
      return [default_song_info], ""
  return [default_song_info], ""


def save_db(history, last_selected=""):
  try:
    data = {"history": history, "last_selected": last_selected}
    with open(DB_FILE, "w", encoding="utf-8") as f:
      json.dump(data, f, ensure_ascii=False, indent=4)
  except Exception as e:
    st.sidebar.error(f"디스크 저장 실패: {e}")


# 오선지 SVG 생성기
def render_diatonic_staff_svg(key_obj):
  tonic_str = key_obj.tonic.name
  mode_str = key_obj.mode.lower()
  is_major = mode_str == "major"

  eng_degrees = [
      "Tonic (으뜸음)",
      "Supertonic (윗으뜸음)",
      "Mediant (가온음)",
      "Subdominant (버금딸림음)",
      "Dominant (딸림음)",
      "Submediant (버금가온음)",
      "Leading-Tone (이끈음)",
  ]

  if is_major:
    sc = scale.MajorScale(key_obj.tonic)
    romans = ["I", "ii", "iii", "IV", "V", "vi", "vii°"]
    funcs = ["T", "S영역", "Dp", "S", "D", "tP", "vii°"]
    title_label = f"{tonic_str} 장조 (Major)"
  else:
    sc = scale.HarmonicMinorScale(key_obj.tonic)
    romans = ["i", "ii°", "III+", "iv", "V", "VI", "vii°"]
    funcs = ["t", "S영역", "tP", "s", "D", "sP", "vii°"]
    title_label = f"{tonic_str} 단조 (Minor - 화성단음계 기준)"

  pitches = sc.getPitches(f"{tonic_str}4", f"{tonic_str}5")[:7]
  step_map = {"C": 0, "D": 1, "E": 2, "F": 3, "G": 4, "A": 5, "B": 6}

  def pitch_to_y(p):
    base_steps = 4 * 7 + 2
    curr_steps = p.octave * 7 + step_map[p.step]
    diff = curr_steps - base_steps
    return 80 - (diff * 5)

  svg_width = 920
  svg_height = 180
  svg = [
      f'<svg width="100%" viewBox="0 0 {svg_width} {svg_height}"'
      ' xmlns="http://www.w3.org/2000/svg" style="background:#ffffff;'
      " border:1px solid #d1d5db; border-radius:8px; margin-bottom:12px;"
      ' box-shadow: 0 1px 3px rgba(0,0,0,0.05);">'
  ]

  svg.append(
      f'<text x="20" y="24" font-size="15" font-weight="bold"'
      f' fill="#1f2937">{title_label}</text>'
  )

  for line_idx in range(5):
    y = 40 + line_idx * 10
    svg.append(
        f'<line x1="20" y1="{y}" x2="{svg_width - 20}" y2="{y}"'
        ' stroke="#6b7280" stroke-width="1"/>'
    )

  svg.append(
      '<text x="22" y="76" font-size="44" font-family="serif"'
      ' fill="#111827">𝄞</text>'
  )

  start_x = 115
  spacing_x = 112

  for idx in range(7):
    cx = start_x + idx * spacing_x
    root_p = pitches[idx]
    third_p = pitches[(idx + 2) % 7]
    if third_p.midi < root_p.midi:
      third_p = third_p.transpose(12)
    fifth_p = pitches[(idx + 4) % 7]
    if fifth_p.midi < third_p.midi:
      fifth_p = fifth_p.transpose(12)

    triad_pitches = [root_p, third_p, fifth_p]
    chord_names = []

    for p in triad_pitches:
      cy = pitch_to_y(p)
      if cy >= 90:
        for ly in range(90, int(cy) + 1, 10):
          svg.append(
              f'<line x1="{cx - 13}" y1="{ly}" x2="{cx + 13}" y2="{ly}"'
              ' stroke="#374151" stroke-width="1"/>'
          )
      elif cy <= 30:
        for ly in range(30, int(cy) - 1, -10):
          svg.append(
              f'<line x1="{cx - 13}" y1="{ly}" x2="{cx + 13}" y2="{ly}"'
              ' stroke="#374151" stroke-width="1"/>'
          )

      acc_text = ""
      if p.accidental is not None:
        if p.accidental.name == "sharp":
          acc_text = "♯"
        elif p.accidental.name == "flat":
          acc_text = "♭"

      if acc_text:
        svg.append(
            f'<text x="{cx - 19}" y="{cy + 4}" font-size="13" fill="#dc2626"'
            f' font-weight="bold">{acc_text}</text>'
        )

      svg.append(
          f'<ellipse cx="{cx}" cy="{cy}" rx="7.2" ry="4.5" fill="transparent"'
          ' stroke="#111827" stroke-width="2"/>'
      )
      chord_names.append(p.name.replace("-", "b"))

    svg.append(
        f'<text x="{cx}" y="115" font-size="14" font-weight="bold"'
        f' text-anchor="middle" fill="#1d4ed8">{romans[idx]} <tspan'
        f' fill="#047857">[{funcs[idx]}]</tspan></text>'
    )
    svg.append(
        f'<text x="{cx}" y="135" font-size="10.5" font-weight="600"'
        f' text-anchor="middle" fill="#111827">{eng_degrees[idx]}</text>'
    )
    svg.append(
        f'<text x="{cx}" y="153" font-size="10" text-anchor="middle"'
        f' fill="#6b7280">({"-".join(chord_names)})</text>'
    )

  svg.append("</svg>")
  return "".join(svg)


# 세션 상태 초기화
if "song_history" not in st.session_state:
  history_loaded, last_selected_loaded = load_db()
  st.session_state["song_history"] = history_loaded
  st.session_state["last_selected_title"] = last_selected_loaded

# 사이드바: 통합 파일 업로더 (.mxl 확장자 완벽 지원)
st.sidebar.header("📁 악보 파일 업로드")
uploaded_file = st.sidebar.file_uploader(
    "MusicXML, MIDI, PDF 파일 업로드",
    type=["musicxml", "xml", "mxl", "mid", "midi", "pdf"],
    key="persistent_file_uploader",
)

if uploaded_file is not None:
  current_title = uploaded_file.name
  existing_titles = [s["title"] for s in st.session_state["song_history"]]

  if current_title not in existing_titles:
    file_extension = current_title.split(".")[-1].lower()

    if file_extension == "pdf":
      pdf_bytes = uploaded_file.getvalue()
      base64_pdf = base64.b64encode(pdf_bytes).decode("utf-8")
      pdf_display = (
          f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%">'
          ' height="600px" type="application/pdf"></iframe>'
      )

      new_song = {
          "composer": "Uploaded PDF",
          "title": current_title,
          "era": "사용자 업로드 PDF 악보",
          "philosophy": "PDF 원본 뷰어 및 연주 참고용 악보",
          "measures": default_song_info["measures"],
          "pdf_display": pdf_display,
      }
      st.session_state["song_history"].append(new_song)
      new_option_str = f"{new_song['title']} ({new_song['composer']})"
      st.session_state["last_selected_title"] = new_option_str
      save_db(st.session_state["song_history"], new_option_str)
      st.sidebar.success(
          f"✨ PDF 악보({current_title})가 영구 보관함에 저장되었습니다!"
      )

    elif file_extension in ["musicxml", "xml", "mxl", "mid", "midi"]:
      try:
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=f".{file_extension}"
        ) as tmp:
          tmp.write(uploaded_file.getvalue())
          tmp_path = tmp.name

        score = converter.parse(tmp_path)
        extracted_measures = []

        try:
          flat_score = score.flatten()
        except:
          flat_score = score

        measures_list = flat_score.getElementsByClass("Measure")

        if measures_list:
          for m in measures_list:
            notes_in_m = []
            for n in m.notes:
              if getattr(n, "isNote", False):
                notes_in_m.append(n.nameWithOctave)
              elif getattr(n, "isChord", False) and n.pitches:
                notes_in_m.append(n.pitches[0].nameWithOctave)
            if notes_in_m:
              extracted_measures.append(notes_in_m[:4])

        if not extracted_measures:
          all_notes = []
          for n in flat_score.notes:
            if getattr(n, "isNote", False):
              all_notes.append(n.nameWithOctave)
            elif getattr(n, "isChord", False) and n.pitches:
              all_notes.append(n.pitches[0].nameWithOctave)

          if all_notes:
            extracted_measures = [
                all_notes[i : i + 4] for i in range(0, len(all_notes), 4)
            ]

        if extracted_measures:
          is_bach = (
              "bach" in current_title.lower()
              or "bwv" in current_title.lower()
          )
          composer_name = (
              "Johann Sebastian Bach" if is_bach else "Uploaded Composer"
          )
          era_desc = (
              "바로크 시대 (1685–1750)" if is_bach else "사용자 업로드 음악 데이터"
          )
          philosophy_desc = (
              "대위법적 선율 진행과 정교한 화성 구조의 조화를 추구함."
              if is_bach
              else "자동 파싱된 악보 데이터 기반 화성 분석"
          )

          new_song = {
              "composer": composer_name,
              "title": current_title,
              "era": era_desc,
              "philosophy": philosophy_desc,
              "measures": extracted_measures,
              "pdf_display": None,
          }
          st.session_state["song_history"].append(new_song)

          new_option_str = f"{new_song['title']} ({new_song['composer']})"
          st.session_state["last_selected_title"] = new_option_str
          save_db(st.session_state["song_history"], new_option_str)
          st.sidebar.success(
              f"✨ 총 {len(extracted_measures)}마디 파싱 완료 & 영구 보관함"
              " 저장!"
          )
        else:
          st.sidebar.warning(
              "⚠️ 파일에서 유효한 음표 데이터를 추출하지 못했습니다."
          )
      except Exception as e:
        st.sidebar.error(f"파싱 오류 발생: {e}")

# 사이드바: 분석 대상 곡 선택 (보관함)
st.sidebar.header("📌 분석 대상 곡 선택 (보관함)")
song_options = [
    f"{s['title']} ({s['composer']})" for s in st.session_state["song_history"]
]

default_index = 0
saved_last_title = st.session_state.get("last_selected_title", "")
if saved_last_title in song_options:
  default_index = song_options.index(saved_last_title)

selected_option = st.sidebar.selectbox(
    "보관된 곡 목록",
    song_options,
    index=default_index,
    key="stable_song_selectbox",
)

if selected_option != saved_last_title:
  st.session_state["last_selected_title"] = selected_option
  save_db(st.session_state["song_history"], selected_option)

selected_index = song_options.index(selected_option)
song_info = st.session_state["song_history"][selected_index]
active_pdf_display = song_info.get("pdf_display", None)

# [Part 0] 작곡가 및 시대적 배경
st.header("😊 [Part 0. 작곡가 및 시대적 배경]")
col1, col2 = st.columns(2)
with col1:
  st.info(f"**작곡가 / 곡명**: {song_info['composer']} - {song_info['title']}")
  st.info(f"**활동 시대**: {song_info['era']}")
with col2:
  st.success(f"**음악적 철학**: {song_info['philosophy']}")

if active_pdf_display is not None:
  st.markdown("---")
  st.header("📖 [업로드된 원본 PDF 악보 뷰어]")
  st.markdown(active_pdf_display, unsafe_allow_html=True)

# [Part 1] 음악적 구조와 전체 마디 화성 분석
st.markdown("---")
st.header("🎹 [Part 1. 음악적 구조 및 정밀 화성 분석]")

total_measures = len(song_info["measures"])

s_full = stream.Stream()
for m_notes in song_info["measures"]:
  _ = s_full.append(chord.Chord(m_notes))

try:
  base_key = s_full.analyze("key")
  base_tonic = base_key.tonic.name
  base_mode = base_key.mode.capitalize()
except:
  base_key = key.Key("C")
  base_tonic = "C"
  base_mode = "Major"

base_key_str = f"{base_tonic} {base_mode}"

table_rows = []
modulation_timeline = []
unique_keys_dict = {base_key_str: base_key}

prev_key_str = base_key_str
mod_start_measure = 1

for i, m_notes in enumerate(song_info["measures"], 1):
  c = chord.Chord(m_notes)

  start_idx = max(0, i - 5)
  end_idx = min(total_measures, i + 4)
  local_stream = stream.Stream()
  for m in song_info["measures"][start_idx:end_idx]:
    _ = local_stream.append(chord.Chord(m))

  try:
    local_key = local_stream.analyze("key")
    curr_key_str = f"{local_key.tonic.name} {local_key.mode.capitalize()}"
  except:
    local_key = base_key
    curr_key_str = prev_key_str

  if curr_key_str not in unique_keys_dict:
    unique_keys_dict[curr_key_str] = local_key

  if curr_key_str != prev_key_str and i > 3:
    modulation_timeline.append(
        f"• **마디 {mod_start_measure} ~ 마디 {i-1}**: `{prev_key_str}`"
        f" ➔ **마디 {i}부터**: `{curr_key_str}` 전조/변조"
    )
    mod_start_measure = i
    prev_key_str = curr_key_str

  try:
    rn = roman.romanNumeralFromChord(c, local_key)
    raw_fig = rn.figure
    fig_clean = raw_fig.replace(" of ", "/").replace(" ", "")

    if "64" in fig_clean:
      fig = fig_clean.replace("64", " 6/4")
    elif "65" in fig_clean:
      fig = fig_clean.replace("65", " 6/5")
    elif "43" in fig_clean:
      fig = fig_clean.replace("43", " 4/3")
    elif "32" in fig_clean or "42" in fig_clean:
      fig = fig_clean.replace("32", " 2").replace("42", " 2")
    elif "6" in fig_clean and "/" not in fig_clean:
      fig = fig_clean.replace("6", " 6")
    elif "7" in fig_clean and "/" not in fig_clean:
      fig = fig_clean.replace("7", " 7")
    else:
      fig = fig_clean

    scale_deg = rn.scaleDegree
  except:
    fig = "-"
    scale_deg = 1

  is_minor_local = local_key.mode.lower() == "minor"
  func_story = (
      "t - Tonic (단조 으뜸음)" if is_minor_local else "T - Tonic (으뜸음)"
  )
  if "/" in fig:
    func_story = "Secondary Dominant (부속화음)"
  elif scale_deg == 2:
    func_story = "S영역 - Supertonic (윗으뜸음)"
  elif scale_deg == 3:
    func_story = (
        "tP - Mediant (가온음)" if is_minor_local else "Dp - Mediant (가온음)"
    )
  elif scale_deg == 4:
    func_story = (
        "s - Subdominant (버금딸림음)"
        if is_minor_local
        else "S - Subdominant (버금딸림음)"
    )
  elif scale_deg == 5:
    func_story = "D - Dominant (딸림음)"
  elif scale_deg == 6:
    func_story = (
        "sP - Submediant (버금가온음)"
        if is_minor_local
        else "tP - Submediant (버금가온음)"
    )
  elif scale_deg == 7:
    func_story = "vii° - Leading-Tone (이끈음)"

  table_rows.append({
      "마디": f"마디 {i}",
      "조성": curr_key_str,
      "구성음": ", ".join(m_notes),
      "로마숫자 화성": fig,
      "베이스음": c.bass().name if c.pitches else "-",
      "화성 기능 (영문/한글)": func_story,
  })

if mod_start_measure < total_measures:
  modulation_timeline.append(
      f"• **주요 유지 구간**: 마디 {mod_start_measure} ~ 마디 {total_measures}"
      f" (`{prev_key_str}`)"
  )

modulated_keys = [k for k in unique_keys_dict.keys() if k != base_key_str]
if modulated_keys:
  mod_display_text = (
      f"{base_key_str} (기본 조성)  ➔  전조 감지 조성:"
      f" {', '.join(modulated_keys)}"
  )
else:
  mod_display_text = f"{base_key_str} (전조 없음 - 단일 조성 유지)"

st.markdown(f"**1. 조성 및 전조 현황 : {mod_display_text}**")

# [접이식 박스] 조성별 오선지 3화음 대조표
with st.expander(
    f"🎼 [조성별 온음표 3화음 & 영문·백병동 화성학 체계"
    f" 펼쳐보기/접기] (총 {len(unique_keys_dict)}개 조성)",
    expanded=True,
):
  st.markdown(
      "현재 곡에 등장하는 **기본 조성**과 **전조된 조성** 각각의"
      " **온음표(Whole Note) 3화음**(오선 실선 관통형) 및 영문 도수명·기능"
      " 기호입니다."
  )

  for idx_k, (k_name, k_obj) in enumerate(unique_keys_dict.items()):
    badge = (
        "🏠 기본 조성 (Home Key)"
        if idx_k == 0
        else "🔀 전조된 조성 (Modulated Key)"
    )
    st.markdown(f"**{badge} : `{k_name}`**")
    staff_svg_html = render_diatonic_staff_svg(k_obj)
    st.markdown(staff_svg_html, unsafe_allow_html=True)

  st.markdown("---")
  st.markdown(
      "📌 **백병동 《전통 화성학》 & 영문 원서 화성 용어 대조표 (별표 박스"
      " 기준)**"
  )
  col_exp1, col_exp2 = st.columns(2)
  with col_exp1:
    st.markdown(
        "**☀️ 장조 (Major Scale)**\n"
        "- **I** [ **T** ] : **Tonic** (으뜸음)\n"
        "- **ii** [ **S영역** ] : **Supertonic** (윗으뜸음)\n"
        "- **iii** [ **Dp** ] : **Mediant** (도미넌트의 패럴랠 / 가온음)\n"
        "- **IV** [ **S** ] : **Subdominant** (버금딸림음)\n"
        "- **V** [ **D** ] : **Dominant** (딸림음)\n"
        "- **vi** [ **tP** ] : **Submediant** (단조 토닉의 패럴랠 / 버금가온음)\n"
        "- **vii°** : **Leading-Tone** (이끈음)"
    )
  with col_exp2:
    st.markdown(
        "**🌙 단조 (Minor Scale)**\n"
        "- **i** [ **t** ] : **Tonic** (단조 토닉 / 으뜸음)\n"
        "- **ii°** [ **S영역** ] : **Supertonic** (윗으뜸음)\n"
        "- **III+** [ **tP** ] : **Mediant** (단조 토닉의 패럴랠 / 가온음)\n"
        "- **iv** [ **s** ] : **Subdominant** (단조 서브도미넌트 / 버금딸림음)\n"
        "- **V** [ **D** ] : **Dominant** (딸림음)\n"
        "- **VI** [ **sP** ] : **Submediant** (단조 서브도미넌트의 패럴랠 /"
        " 버금가온음)\n"
        "- **vii°** : **Leading-Tone** (이끈음)"
    )

st.markdown(f"**2. 구조 분석 : 총 {total_measures}마디 정통 화성학 기준 분석 완료**")

df_analysis = pd.DataFrame(table_rows)

st.subheader("🗺️ [핵심 전조 및 조성 변화 타임라인 요약]")
if len(modulation_timeline) > 1:
  for item in modulation_timeline:
    st.markdown(item)
else:
  st.info(
      f"이 곡은 전체 구간 동안 **{base_key_str}** 조성이 안정적으로"
      " 유지됩니다."
  )

st.markdown("---")
st.subheader(f"📊 전체 {total_measures}마디 상세 분석 표")
st.dataframe(df_analysis, width=1200, height=550, hide_index=True)

# [Part 2] 연주 해석 체크리스트
st.markdown("---")
st.header("🎭 [Part 2. 연주 해석 및 작곡가의 의도 체크리스트]")
st.warning(
    "**⑩ 긴장과 해소**: Dominant(V) 및 Secondary Dominant(V/V 등)에서 목표"
    " 화성으로 해결될 때의 긴장감과 호흡을 어떻게 살릴 것인가?"
)
st.warning(
    "**⑫ 전조 및 변조 해석**: 곡 중간의 조성 변화 구간에서 프레이징의 색깔과"
    " 음색을 어떻게 전환할 것인가?"
)

# 💾 분석 결과 저장 및 관리
st.markdown("---")
st.header("💾 분석 결과 저장 및 관리")
col_save1, col_save2 = st.columns(2)

with col_save1:
  csv_content = "마디,조성,구성음,로마숫자화성,베이스음,화성기능\n"
  for row in table_rows:
    csv_content += (
        f"{row['마디']},{row['조성']},{row['구성음']},{row['로마숫자 화성']},"
        f"{row['베이스음']},{row['화성 기능 (영문/한글)']}\n"
    )

  st.download_button(
      label="📥 분석 결과 CSV 파일로 다운로드",
      data=csv_content.encode("utf-8-sig"),
      file_name=f"Harmonic_Analysis_{song_info['title']}.csv",
      mime="text/csv",
  )

with col_save2:
  if "saved_analyses" not in st.session_state:
    st.session_state["saved_analyses"] = []

  if st.button("📌 현재 분석 내용을 웹 세션에 저장"):
    record = {
        "title": song_info["title"],
        "measures_count": total_measures,
        "key": mod_display_text,
    }
    st.session_state["saved_analyses"].append(record)
    st.success("웹 세션 메모리에 저장되었습니다!")

if st.session_state.get("saved_analyses"):
  with st.expander("📂 웹 세션에 저장된 분석 기록 목록"):
    for idx, rec in enumerate(st.session_state["saved_analyses"], 1):
      st.markdown(
          f"**{idx}. 곡명**: {rec['title']} ({rec['measures_count']}마디) |"
          f" **조성현황**: {rec['key']}"
      )