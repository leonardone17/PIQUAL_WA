from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterator, Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    select,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

Base = declarative_base()


class Evaluator(Base):
    __tablename__ = "evaluators"

    id = Column(Integer, primary_key=True)
    evaluator_id = Column(String(100), unique=True, nullable=False, index=True)
    nome = Column(String(255), nullable=False)
    cognome = Column(String(255), nullable=False)
    anni_esperienza = Column(String(50), nullable=False)
    stato_professionale = Column(String(50), nullable=False)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)

    responses = relationship("CaseResponse", back_populates="evaluator", cascade="all, delete-orphan")


class CaseResponse(Base):
    __tablename__ = "case_responses"
    __table_args__ = (UniqueConstraint("evaluator_id", "case_name", name="uq_evaluator_case"),)

    id = Column(Integer, primary_key=True)
    evaluator_id = Column(Integer, ForeignKey("evaluators.id"), nullable=False, index=True)
    case_name = Column(String(255), nullable=False, index=True)
    case_prefix = Column(String(50), nullable=False)

    T2_Req_Spessore3mm = Column(String(10), nullable=True)
    T2_Item1_SNR_assiale = Column(String(10), nullable=True)
    T2_Item2_Delineazione_strutture = Column(String(10), nullable=True)
    T2_Item3_Artefatti_assiale = Column(String(10), nullable=True)
    T2_Item4_SagCor_adeguato = Column(String(10), nullable=True)
    T2_Totale = Column(Integer, nullable=True)

    DWI_Req_SpessoreLE4mm = Column(String(10), nullable=True)
    DWI_Req_Bhigh_GE1400 = Column(String(10), nullable=True)
    DWI_Req_ADC_due_b_fino1000 = Column(String(10), nullable=True)
    DWI_Item1_Contrasto_SNR_b_alto = Column(String(10), nullable=True)
    DWI_Item2_Contrasto_ADC_TZ_BPH_PZ = Column(String(10), nullable=True)
    DWI_Item3_Artefatti_regione_prostatica = Column(String(10), nullable=True)
    DWI_Item4_Corrispondenza_ADC_balto_con_T2AX = Column(String(10), nullable=True)
    DWI_Totale = Column(Integer, nullable=True)

    DCE_Req_Spessore3mm = Column(String(10), nullable=True)
    DCE_Req_RisoluzioneTemporaleLE15s = Column(String(10), nullable=True)
    DCE_Req_FatSat_o_PostProcessing = Column(String(10), nullable=True)
    DCE_Item1_Artefatti_e_Bolo = Column(String(10), nullable=True)
    DCE_Item2_Strutture_anatomiche_identificabili = Column(String(10), nullable=True)
    DCE_Totale = Column(String(10), nullable=True)

    PIQUAL_Finale = Column(String(10), nullable=True)
    completed = Column(Boolean, nullable=False, default=False)
    first_saved_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)

    evaluator = relationship("Evaluator", back_populates="responses")


@dataclass
class EvaluatorProfile:
    evaluator_id: str
    nome: str
    cognome: str
    anni_esperienza: str
    stato_professionale: str


class DatabaseManager:
    def __init__(self, database_url: str):
        self.engine = create_engine(database_url, pool_pre_ping=True)
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)
        Base.metadata.create_all(self.engine)

    @contextmanager
    def session(self) -> Iterator:
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def load_evaluator_profile(self, evaluator_id: str) -> Optional[Dict[str, str]]:
        with self.session() as session:
            evaluator = session.execute(
                select(Evaluator).where(Evaluator.evaluator_id == evaluator_id)
            ).scalar_one_or_none()
            if evaluator is None:
                return None
            return {
                "ID_valutatore": evaluator.evaluator_id,
                "Nome": evaluator.nome,
                "Cognome": evaluator.cognome,
                "Anni_esperienza_TSRM": evaluator.anni_esperienza,
                "Stato_professionale": evaluator.stato_professionale,
            }

    def load_case_response(self, evaluator_id: str, case_name: str) -> Optional[Dict[str, str]]:
        with self.session() as session:
            evaluator = session.execute(
                select(Evaluator).where(Evaluator.evaluator_id == evaluator_id)
            ).scalar_one_or_none()
            if evaluator is None:
                return None
            response = session.execute(
                select(CaseResponse).where(
                    CaseResponse.evaluator_id == evaluator.id,
                    CaseResponse.case_name == case_name,
                )
            ).scalar_one_or_none()
            if response is None:
                return None
            return self._response_to_dict(response)

    def load_all_case_status(self, evaluator_id: str) -> Dict[str, bool]:
        with self.session() as session:
            evaluator = session.execute(
                select(Evaluator).where(Evaluator.evaluator_id == evaluator_id)
            ).scalar_one_or_none()
            if evaluator is None:
                return {}
            rows = session.execute(
                select(CaseResponse.case_name, CaseResponse.completed).where(CaseResponse.evaluator_id == evaluator.id)
            ).all()
            return {case_name: bool(completed) for case_name, completed in rows}

    def upsert_case_response(
        self,
        profile: EvaluatorProfile,
        case_name: str,
        case_prefix: str,
        answers: Dict[str, str],
        completed: bool,
    ) -> str:
        now = datetime.utcnow()
        with self.session() as session:
            evaluator = session.execute(
                select(Evaluator).where(Evaluator.evaluator_id == profile.evaluator_id)
            ).scalar_one_or_none()

            if evaluator is None:
                evaluator = Evaluator(
                    evaluator_id=profile.evaluator_id,
                    nome=profile.nome,
                    cognome=profile.cognome,
                    anni_esperienza=profile.anni_esperienza,
                    stato_professionale=profile.stato_professionale,
                    created_at=now,
                    updated_at=now,
                )
                session.add(evaluator)
                session.flush()
            else:
                evaluator.nome = profile.nome
                evaluator.cognome = profile.cognome
                evaluator.anni_esperienza = profile.anni_esperienza
                evaluator.stato_professionale = profile.stato_professionale
                evaluator.updated_at = now

            response = session.execute(
                select(CaseResponse).where(
                    CaseResponse.evaluator_id == evaluator.id,
                    CaseResponse.case_name == case_name,
                )
            ).scalar_one_or_none()

            created = response is None
            if response is None:
                response = CaseResponse(
                    evaluator_id=evaluator.id,
                    case_name=case_name,
                    case_prefix=case_prefix,
                    first_saved_at=now,
                    updated_at=now,
                )
                session.add(response)

            for field, value in answers.items():
                if hasattr(response, field):
                    setattr(response, field, value)
            response.completed = bool(completed)
            response.updated_at = now

            session.flush()
            return "creato" if created else "aggiornato"

    def _response_to_dict(self, response: CaseResponse) -> Dict[str, str]:
        mapping = {
            "T2_Req_Spessore3mm": response.T2_Req_Spessore3mm,
            "T2_Item1_SNR_assiale": response.T2_Item1_SNR_assiale,
            "T2_Item2_Delineazione_strutture": response.T2_Item2_Delineazione_strutture,
            "T2_Item3_Artefatti_assiale": response.T2_Item3_Artefatti_assiale,
            "T2_Item4_SagCor_adeguato": response.T2_Item4_SagCor_adeguato,
            "DWI_Req_SpessoreLE4mm": response.DWI_Req_SpessoreLE4mm,
            "DWI_Req_Bhigh_GE1400": response.DWI_Req_Bhigh_GE1400,
            "DWI_Req_ADC_due_b_fino1000": response.DWI_Req_ADC_due_b_fino1000,
            "DWI_Item1_Contrasto_SNR_b_alto": response.DWI_Item1_Contrasto_SNR_b_alto,
            "DWI_Item2_Contrasto_ADC_TZ_BPH_PZ": response.DWI_Item2_Contrasto_ADC_TZ_BPH_PZ,
            "DWI_Item3_Artefatti_regione_prostatica": response.DWI_Item3_Artefatti_regione_prostatica,
            "DWI_Item4_Corrispondenza_ADC_balto_con_T2AX": response.DWI_Item4_Corrispondenza_ADC_balto_con_T2AX,
            "DCE_Req_Spessore3mm": response.DCE_Req_Spessore3mm,
            "DCE_Req_RisoluzioneTemporaleLE15s": response.DCE_Req_RisoluzioneTemporaleLE15s,
            "DCE_Req_FatSat_o_PostProcessing": response.DCE_Req_FatSat_o_PostProcessing,
            "DCE_Item1_Artefatti_e_Bolo": response.DCE_Item1_Artefatti_e_Bolo,
            "DCE_Item2_Strutture_anatomiche_identificabili": response.DCE_Item2_Strutture_anatomiche_identificabili,
            "T2_Totale": str(response.T2_Totale or ""),
            "DWI_Totale": str(response.DWI_Totale or ""),
            "DCE_Totale": str(response.DCE_Totale or ""),
            "PIQUAL_Finale": str(response.PIQUAL_Finale or ""),
            "completed": "1" if response.completed else "0",
        }
        return {k: ("" if v is None else str(v)) for k, v in mapping.items()}
