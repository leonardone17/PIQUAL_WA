from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List

import streamlit as st
from PIL import Image
from sqlalchemy import select

from db import DatabaseManager, Evaluator, EvaluatorProfile
from local_repository import DISPLAY_SEQUENCES, CaseData, LocalCaseRepository
from scoring import compute_dce_total, compute_dwi_total, compute_piqual_final, compute_t2_total, required_fields_complete

APP_TITLE = "PI-QUAL 2 Viewer Web"
DEFAULT_CASE_ROOT = "CASI_RM"
EVALUATOR_ID_PREFIX = "TSRM"
EVALUATOR_ID_WIDTH = 3
FORCED_YES_FIELDS = {
    "T2_Req_Spessore3mm",
    "DWI_Req_SpessoreLE4mm",
    "DWI_Req_Bhigh_GE1400",
    "DWI_Req_ADC_due_b_fino1000",
    "DCE_Req_Spessore3mm",
    "DCE_Req_RisoluzioneTemporaleLE15s",
}

QUESTION_SPECS = {
    "T2_Req_Spessore3mm": ("Prerequisito essenziale: spessore della fetta 3 mm", ["Sì", "No"]),
    "T2_Item1_SNR_assiale": ("T2-WI assiale: adeguato rapporto segnale/rumore (SNR) in tutte le parti delle immagini", ["1", "0"]),
    "T2_Item2_Delineazione_strutture": ("T2-WI assiale: capacità di delineare chiaramente le strutture rilevanti nella prostata", ["1", "0"]),
    "T2_Item3_Artefatti_assiale": ("T2-WI assiale: assenza di artefatti significativi nella regione prostatica", ["1", "0"]),
    "T2_Item4_SagCor_adeguato": ("Sagittale o coronale: SNR e risoluzione adeguati e assenza di artefatti significativi", ["1", "0"]),
    "DWI_Req_SpessoreLE4mm": ("Prerequisito: spessore della fetta ≤ 4 mm", ["Sì", "No"]),
    "DWI_Req_Bhigh_GE1400": ("Prerequisito: sequenza ad alto valore b ≥ 1400 s/mm²", ["Sì", "No"]),
    "DWI_Req_ADC_due_b_fino1000": ("Prerequisito: mappa ADC con almeno due valori di b fino a 1000 s/mm²", ["Sì", "No"]),
    "DWI_Item1_Contrasto_SNR_b_alto": ("Contrasto e SNR adeguati sulle immagini ad alto valore di b", ["1", "0"]),
    "DWI_Item2_Contrasto_ADC_TZ_BPH_PZ": ("Intervallo di contrasto adeguato per differenziare TZ/BPH da PZ sulle mappe ADC", ["1", "0"]),
    "DWI_Item3_Artefatti_regione_prostatica": ("Assenza di artefatti significativi nella regione prostatica", ["1", "0"]),
    "DWI_Item4_Corrispondenza_ADC_balto_con_T2AX": ("Corrispondenza anatomica della mappa ADC / sequenza ad alto valore b con la T2-WI assiale", ["1", "0"]),
    "DCE_Req_Spessore3mm": ("Prerequisito: spessore della fetta 3 mm", ["Sì", "No"]),
    "DCE_Req_RisoluzioneTemporaleLE15s": ("Prerequisito: risoluzione temporale ≤ 15 secondi", ["Sì", "No"]),
    "DCE_Req_FatSat_o_PostProcessing": ("Prerequisito: saturazione del grasso o post-elaborazione adeguata", ["Sì", "No"]),
    "DCE_Item1_Artefatti_e_Bolo": ("Assenza di artefatti significativi nella regione prostatica e adeguato potenziamento del bolo", ["+", "-"]),
    "DCE_Item2_Strutture_anatomiche_identificabili": ("Capacità di identificare strutture anatomiche (es. vasi capsulari o arteria pudenda)", ["+", "-"]),
}
FIELD_ORDER = list(QUESTION_SPECS.keys())


def get_db_url() -> str:
    if "database_url" in st.secrets:
        return st.secrets["database_url"]
    postgres = st.secrets.get("postgres", None)
    if postgres and "url" in postgres:
        return postgres["url"]
    raise RuntimeError("database_url mancante nelle secrets di Streamlit.")


@st.cache_resource(show_spinner=False)
def get_db() -> DatabaseManager:
    return DatabaseManager(get_db_url())


@st.cache_resource(show_spinner=False)
def get_cases(case_root: str) -> List[CaseData]:
    return LocalCaseRepository(case_root).load_cases()


@st.cache_data(show_spinner=False, max_entries=4096)
def load_image(path: str) -> Image.Image:
    return Image.open(path).convert("L")


def get_case_root() -> str:
    if "case_root" in st.secrets:
        return st.secrets["case_root"]
    return DEFAULT_CASE_ROOT


def widget_key(case: CaseData, field_key: str) -> str:
    return f"{case.excel_prefix}__{field_key}"


def answer_from_state(case: CaseData, field_key: str) -> str:
    return str(st.session_state.get(widget_key(case, field_key), "")).strip()


def enforce_forced_yes_for_case(case: CaseData):
    for field_key in FORCED_YES_FIELDS:
        st.session_state[widget_key(case, field_key)] = "Sì"


def enforce_forced_yes_defaults(cases: List[CaseData]):
    for case in cases:
        enforce_forced_yes_for_case(case)


def fields_complete(case: CaseData) -> bool:
    return required_fields_complete(lambda key: answer_from_state(case, key))


def set_answers_from_db(case: CaseData, data: Dict[str, str]):
    for field_key in FIELD_ORDER:
        if field_key in FORCED_YES_FIELDS:
            st.session_state[widget_key(case, field_key)] = "Sì"
            continue
        value = str(data.get(field_key, "")).strip()
        if value:
            st.session_state[widget_key(case, field_key)] = value


def suggest_next_evaluator_id() -> str:
    db = get_db()
    used_ids = set()
    pattern = re.compile(rf"^{re.escape(EVALUATOR_ID_PREFIX)}(\d+)$")

    with db.session() as session:
        rows = session.execute(select(Evaluator.evaluator_id)).all()
        for (value,) in rows:
            if value:
                used_ids.add(str(value).strip())

    max_seen = 0
    used_numbers = set()
    for value in used_ids:
        match = pattern.match(value)
        if match:
            number = int(match.group(1))
            used_numbers.add(number)
            max_seen = max(max_seen, number)

    for number in range(1, max_seen + 2):
        if number not in used_numbers:
            return f"{EVALUATOR_ID_PREFIX}{number:0{EVALUATOR_ID_WIDTH}d}"

    return f"{EVALUATOR_ID_PREFIX}{1:0{EVALUATOR_ID_WIDTH}d}"


def assign_next_evaluator_id(force: bool = False):
    current_value = st.session_state.get("eval_id", "").strip()
    if current_value and not force:
        return
    st.session_state.eval_id = suggest_next_evaluator_id()


def init_session_state(cases: List[CaseData]):
    st.session_state.setdefault("current_case_index", 0)
    st.session_state.setdefault("eval_id", "")
    st.session_state.setdefault("eval_nome", "")
    st.session_state.setdefault("eval_cognome", "")
    st.session_state.setdefault("eval_esperienza", "")
    st.session_state.setdefault("eval_stato", "")
    st.session_state.setdefault("last_message", None)
    st.session_state.setdefault("saved_once", {case.folder_name: False for case in cases})
    st.session_state.setdefault("case_status", {})

    for case in cases:
        st.session_state["saved_once"].setdefault(case.folder_name, False)
        seq_key = f"selected_sequence__{case.folder_name}"
        if seq_key not in st.session_state:
            available = [seq for seq in DISPLAY_SEQUENCES if seq in case.sequences]
            st.session_state[seq_key] = available[0] if available else ""
        for seq_name in DISPLAY_SEQUENCES:
            state_key = f"slice_idx_state__{case.folder_name}__{seq_name}"
            st.session_state.setdefault(state_key, 0)
        for field_key in FIELD_ORDER:
            default_value = "Sì" if field_key in FORCED_YES_FIELDS else ""
            st.session_state.setdefault(widget_key(case, field_key), default_value)

    enforce_forced_yes_defaults(cases)


def load_evaluator_data(cases: List[CaseData]):
    evaluator_id = st.session_state.get("eval_id", "").strip()
    if not evaluator_id:
        st.session_state.last_message = ("warning", "Inserisci prima ID valutatore.")
        return

    db = get_db()
    profile = db.load_evaluator_profile(evaluator_id)
    if not profile:
        st.session_state.last_message = ("warning", f"Nessun valutatore trovato con ID {evaluator_id}.")
        return

    st.session_state["eval_nome"] = profile["Nome"]
    st.session_state["eval_cognome"] = profile["Cognome"]
    st.session_state["eval_esperienza"] = profile["Anni_esperienza_TSRM"]
    st.session_state["eval_stato"] = profile["Stato_professionale"]

    statuses = db.load_all_case_status(evaluator_id)
    st.session_state["case_status"] = statuses
    saved_once = st.session_state.get("saved_once", {})

    for case in cases:
        saved_once[case.folder_name] = case.folder_name in statuses
        case_data = db.load_case_response(evaluator_id, case.folder_name)
        if case_data:
            set_answers_from_db(case, case_data)

    st.session_state["saved_once"] = saved_once
    enforce_forced_yes_defaults(cases)
    st.session_state["last_message"] = ("success", "Dati del valutatore caricati.")


def build_profile() -> EvaluatorProfile | None:
    evaluator_id = st.session_state.eval_id.strip()
    nome = st.session_state.eval_nome.strip()
    cognome = st.session_state.eval_cognome.strip()
    esperienza = str(st.session_state.eval_esperienza).strip()
    stato = st.session_state.eval_stato.strip()
    if not all([evaluator_id, nome, cognome, esperienza, stato]):
        return None
    return EvaluatorProfile(
        evaluator_id=evaluator_id,
        nome=nome,
        cognome=cognome,
        anni_esperienza=esperienza,
        stato_professionale=stato,
    )


def get_case_answers(case: CaseData) -> Dict[str, str]:
    getter = lambda key: answer_from_state(case, key)
    complete = fields_complete(case)
    answers = {field: getter(field) for field in FIELD_ORDER}
    answers["T2_Totale"] = str(compute_t2_total(getter))
    answers["DWI_Totale"] = str(compute_dwi_total(getter))
    answers["DCE_Totale"] = compute_dce_total(getter)
    answers["PIQUAL_Finale"] = compute_piqual_final(getter, has_dce_sequence=("DCE" in case.sequences), fields_complete=complete)
    return answers


def can_open_case(case_index: int, cases: List[CaseData]) -> bool:
    if case_index <= 0:
        return True
    prev_case = cases[case_index - 1]
    return bool(st.session_state.saved_once.get(prev_case.folder_name, False) and st.session_state.case_status.get(prev_case.folder_name, False))


def save_current_case(case: CaseData):
    profile = build_profile()
    if profile is None:
        st.session_state.last_message = ("error", "Compila tutti i dati del valutatore prima di salvare.")
        return

    answers = get_case_answers(case)
    complete = fields_complete(case)
    result = get_db().upsert_case_response(profile, case.folder_name, case.excel_prefix, answers, complete)
    st.session_state.saved_once[case.folder_name] = True
    st.session_state.case_status[case.folder_name] = complete
    st.session_state.last_message = (
        "success",
        f"Caso {case.folder_name} {result}. Stato: {'completato' if complete else 'salvato ma incompleto'}."
    )


def show_case_navigation(cases: List[CaseData]):
    st.markdown("### Casi")
    cols = st.columns(min(len(cases), 6) or 1)
    for idx, case in enumerate(cases):
        label = case.folder_name
        if st.session_state.case_status.get(case.folder_name):
            label += " ✅"
        elif st.session_state.saved_once.get(case.folder_name):
            label += " 🟡"
        else:
            label += " ⚪"
        disabled = not can_open_case(idx, cases)
        col = cols[idx % len(cols)]
        if col.button(label, key=f"btn_case_{idx}", use_container_width=True, disabled=disabled):
            st.session_state.current_case_index = idx
            st.rerun()


def _step_slice(slider_key: str, delta: int, max_idx: int):
    current = int(st.session_state.get(slider_key, 0))
    st.session_state[slider_key] = max(0, min(current + delta, max_idx))


def render_sequence_viewer(case: CaseData):
    st.markdown(f"### {case.folder_name}")
    available = [seq for seq in DISPLAY_SEQUENCES if seq in case.sequences]
    selected = st.radio(
        "Sequenza",
        options=available,
        key=f"selected_sequence__{case.folder_name}",
        horizontal=True,
    )

    paths = case.sequences[selected]
    total = len(paths)
    if total == 0:
        st.warning("Nessuna immagine trovata per questa sequenza.")
        return

    slider_key = f"slice_idx__{case.folder_name}__{selected}"
    if slider_key not in st.session_state:
        st.session_state[slider_key] = 0

    st.session_state[slider_key] = max(0, min(int(st.session_state[slider_key]), total - 1))

    c1, c2, c3 = st.columns([1, 4, 1])

    with c1:
        st.button(
            "◀ Prev",
            key=f"prev_{case.folder_name}_{selected}",
            use_container_width=True,
            disabled=st.session_state[slider_key] <= 0,
            on_click=_step_slice,
            args=(slider_key, -1, total - 1),
        )

    with c2:
        st.slider(
            "Slice",
            min_value=0,
            max_value=total - 1,
            key=slider_key,
            label_visibility="collapsed",
        )

    with c3:
        st.button(
            "Next ▶",
            key=f"next_{case.folder_name}_{selected}",
            use_container_width=True,
            disabled=st.session_state[slider_key] >= total - 1,
            on_click=_step_slice,
            args=(slider_key, 1, total - 1),
        )

    idx = int(st.session_state[slider_key])
    st.caption(f"Slice {idx + 1} / {total}")
    image = load_image(str(paths[idx]))
    st.image(image, use_container_width=True)


def render_fixed_yes_question(case: CaseData, key: str):
    label, options = QUESTION_SPECS[key]
    st.session_state[widget_key(case, key)] = "Sì"
    st.radio(
        label,
        options=options,
        index=0,
        key=widget_key(case, key),
        disabled=True,
    )


def render_editable_question(case: CaseData, key: str):
    label, options = QUESTION_SPECS[key]
    current = answer_from_state(case, key)
    index = options.index(current) if current in options else None
    st.radio(label, options=options, index=index, key=widget_key(case, key))


def render_questionnaire(case: CaseData):
    enforce_forced_yes_for_case(case)
    st.markdown("### Questionario PI-QUAL 2.1")
    with st.form(key=f"form_{case.folder_name}"):
        st.markdown("**T2-WI**")
        render_fixed_yes_question(case, "T2_Req_Spessore3mm")
        for key in [
            "T2_Item1_SNR_assiale",
            "T2_Item2_Delineazione_strutture",
            "T2_Item3_Artefatti_assiale",
            "T2_Item4_SagCor_adeguato",
        ]:
            render_editable_question(case, key)

        st.markdown("**DWI**")
        for key in [
            "DWI_Req_SpessoreLE4mm",
            "DWI_Req_Bhigh_GE1400",
            "DWI_Req_ADC_due_b_fino1000",
        ]:
            render_fixed_yes_question(case, key)
        for key in [
            "DWI_Item1_Contrasto_SNR_b_alto",
            "DWI_Item2_Contrasto_ADC_TZ_BPH_PZ",
            "DWI_Item3_Artefatti_regione_prostatica",
            "DWI_Item4_Corrispondenza_ADC_balto_con_T2AX",
        ]:
            render_editable_question(case, key)

        st.markdown("**DCE**")
        for key in [
            "DCE_Req_Spessore3mm",
            "DCE_Req_RisoluzioneTemporaleLE15s",
        ]:
            render_fixed_yes_question(case, key)
        for key in [
            "DCE_Req_FatSat_o_PostProcessing",
            "DCE_Item1_Artefatti_e_Bolo",
            "DCE_Item2_Strutture_anatomiche_identificabili",
        ]:
            render_editable_question(case, key)

        answers = get_case_answers(case)
        st.info(
            f"T2 totale: {answers['T2_Totale']} | "
            f"DWI totale: {answers['DWI_Totale']} | "
            f"DCE totale: {answers['DCE_Totale']} | "
            f"PI-QUAL finale: {answers['PIQUAL_Finale'] or 'non disponibile finché il caso è incompleto'}"
        )
        submitted = st.form_submit_button("Salva caso", use_container_width=True)

    if submitted:
        save_current_case(case)
        st.rerun()


def main():
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    st.title(APP_TITLE)
    st.caption("Versione web semplice: immagini dal repository, risposte su PostgreSQL.")

    try:
        case_root = get_case_root()
        cases = get_cases(case_root)
        if not cases:
            st.error(f"Nessun caso trovato in {case_root}")
            return
    except Exception as exc:
        st.error(f"Errore nel caricamento dei casi: {exc}")
        return

    try:
        _db = get_db()
    except Exception as exc:
        st.error(f"Errore connessione database: {exc}")
        return

    init_session_state(cases)
    assign_next_evaluator_id(force=False)

    with st.sidebar:
        st.header("Valutatore")
        c_id1, c_id2 = st.columns([3, 1])
        with c_id1:
            st.text_input("ID valutatore", key="eval_id")
        with c_id2:
            st.write("")
            st.write("")
            if st.button("Nuovo ID", use_container_width=True):
                assign_next_evaluator_id(force=True)
                st.rerun()

        st.caption(f"Prossimo ID automatico con prefisso {EVALUATOR_ID_PREFIX} e esclusione degli ID già usati.")
        st.text_input("Nome", key="eval_nome")
        st.text_input("Cognome", key="eval_cognome")
        st.text_input("Anni esperienza TSRM", key="eval_esperienza")
        st.selectbox("Stato professionale", ["", "Studente", "Professionista"], key="eval_stato")
        st.button(
            "Carica dati esistenti",
            use_container_width=True,
            on_click=load_evaluator_data,
            args=(cases,),
        )
        st.divider()
        st.write(f"Cartella casi: `{Path(case_root)}`")

    if st.session_state.last_message:
        level, message = st.session_state.last_message
        getattr(st, level)(message)

    show_case_navigation(cases)
    current_case = cases[st.session_state.current_case_index]

    col1, col2 = st.columns([1.15, 1])
    with col1:
        render_sequence_viewer(current_case)
    with col2:
        render_questionnaire(current_case)


if __name__ == "__main__":
    main()
