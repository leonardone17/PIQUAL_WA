from __future__ import annotations

from typing import Callable


QUESTION_KEYS = [
    "T2_Req_Spessore3mm",
    "T2_Item1_SNR_assiale",
    "T2_Item2_Delineazione_strutture",
    "T2_Item3_Artefatti_assiale",
    "T2_Item4_SagCor_adeguato",
    "DWI_Req_SpessoreLE4mm",
    "DWI_Req_Bhigh_GE1400",
    "DWI_Req_ADC_due_b_fino1000",
    "DWI_Item1_Contrasto_SNR_b_alto",
    "DWI_Item2_Contrasto_ADC_TZ_BPH_PZ",
    "DWI_Item3_Artefatti_regione_prostatica",
    "DWI_Item4_Corrispondenza_ADC_balto_con_T2AX",
    "DCE_Req_Spessore3mm",
    "DCE_Req_RisoluzioneTemporaleLE15s",
    "DCE_Req_FatSat_o_PostProcessing",
    "DCE_Item1_Artefatti_e_Bolo",
    "DCE_Item2_Strutture_anatomiche_identificabili",
]


def compute_t2_total(answer_getter: Callable[[str], str]) -> int:
    if answer_getter("T2_Req_Spessore3mm") != "Sì":
        return 0
    total = 0
    for key in [
        "T2_Item1_SNR_assiale",
        "T2_Item2_Delineazione_strutture",
        "T2_Item3_Artefatti_assiale",
        "T2_Item4_SagCor_adeguato",
    ]:
        value = answer_getter(key)
        if value in {"0", "1"}:
            total += int(value)
    return total


def compute_dwi_total(answer_getter: Callable[[str], str]) -> int:
    req_values = [
        answer_getter("DWI_Req_SpessoreLE4mm"),
        answer_getter("DWI_Req_Bhigh_GE1400"),
        answer_getter("DWI_Req_ADC_due_b_fino1000"),
    ]
    if any(value != "Sì" for value in req_values):
        return 0
    total = 0
    for key in [
        "DWI_Item1_Contrasto_SNR_b_alto",
        "DWI_Item2_Contrasto_ADC_TZ_BPH_PZ",
        "DWI_Item3_Artefatti_regione_prostatica",
        "DWI_Item4_Corrispondenza_ADC_balto_con_T2AX",
    ]:
        value = answer_getter(key)
        if value in {"0", "1"}:
            total += int(value)
    return total


def compute_dce_total(answer_getter: Callable[[str], str]) -> str:
    req_values = [
        answer_getter("DCE_Req_Spessore3mm"),
        answer_getter("DCE_Req_RisoluzioneTemporaleLE15s"),
        answer_getter("DCE_Req_FatSat_o_PostProcessing"),
    ]
    if any(value != "Sì" for value in req_values):
        return "-"
    item1 = answer_getter("DCE_Item1_Artefatti_e_Bolo")
    item2 = answer_getter("DCE_Item2_Strutture_anatomiche_identificabili")
    return "+" if item1 == "+" and item2 == "+" else "-"


def compute_bp_piqual(t2_total: int, dwi_total: int) -> str:
    if t2_total <= 2 or dwi_total <= 2:
        return "1"
    if t2_total == 4 and dwi_total == 4:
        return "3"
    return "2"


def compute_piqual_final(answer_getter: Callable[[str], str], has_dce_sequence: bool, fields_complete: bool) -> str:
    if not fields_complete:
        return ""

    t2_total = compute_t2_total(answer_getter)
    dwi_total = compute_dwi_total(answer_getter)
    dce_total = compute_dce_total(answer_getter)

    if not has_dce_sequence:
        return compute_bp_piqual(t2_total, dwi_total)

    if t2_total <= 2 or dwi_total <= 2:
        if dce_total == "+" and (t2_total == 4 or dwi_total == 4):
            return "2"
        return "1"
    if t2_total == 4 and dwi_total == 4:
        return "3" if dce_total == "+" else "2"
    return "2"


def required_fields_complete(answer_getter: Callable[[str], str]) -> bool:
    return all(bool(answer_getter(key).strip()) for key in QUESTION_KEYS)
