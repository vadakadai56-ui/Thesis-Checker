"""Generate engine/thesischeck/data/uk_us_pairs.tsv (used by CONS-01).

    python tools/make_spelling_pairs.py      (run from engine/)

Each line: UK spelling <TAB> US spelling <TAB> group.
  group "ize"   = -ise/-ize verbs. Oxford spelling legitimately mixes -ize with
                  UK forms like "colour", so this group is checked on its own.
  group "other" = everything else (-our/-or, -re/-er, -ll-/-l-, …).

Words whose US form is ALSO correct British English with another meaning are left
out on purpose (program/programme, licence/license, meter/metre, practise/practice,
check/cheque, tire/tyre, draft/draught, dialog/dialogue).
"""

from __future__ import annotations

from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "thesischeck" / "data" / "uk_us_pairs.tsv"

# -ise verb stems. N = also has an -isation noun, R = also has an -iser agent noun.
ISE_STEMS = """
organ NR; real N; recogn N; character N; priorit N; optim NR; minim N; maxim N; util N;
summar N; emphas; standard N; normal NR; visual NR; categor N; final N; initial NR;
custom NR; special N; general N; author N; apolog; critic; memor N; modern N;
synchron NR; symbol N; stabil NR; social N; mobil N; local N; legal N; global N;
formal N; digit NR; central N; capital N; hospital N; industrial N; internal N; jeopard;
legitim N; liberal N; material N; monet N; neutral N; parameter N; penal; personal N;
polar N; popular N; privat N; public; rational N; revolution; sanit NR; scrutin;
serial NR; subsid; sympath; token NR; trivial N; vandal; vector N; virtual N; vocal N;
energ; harmon N; hypothes; ideal N; immun N; item N; random NR; regular N; patron;
quant N; theor; union N; urban N; western N; fertil NR; familiar N; equal NR; dramat N;
demon N; crystall N; colon N; civil N; canon N; agon; antagon; atom NR; caramel N;
motor N; commercial N; compartmental N; conceptual N; contextual N; decentral N;
democrat N; desensit N; deserial NR; homogen N; individual N; institutional N;
international N; lexical N; marginal N; miniatur N; modular N; natural N; nation N;
operational N; polymer N; pressur N; radical N; reorgan NR; sensit N; steril NR;
synthes R; tantal; terror; weapon N; galvan N; hybrid N; magnet N; mechan N; mineral N;
monopol N; moral; mesmer; ostrac; oxid N; pasteur N; plagiar; proselyt; satir; scandal;
stigmat N; systemat N; textual N; traumat; tyrann; verbal N; victim; vulcan N;
extern N; fantas; fictional N; fossil N; hypnot; idol; immortal; incentiv; ion NR;
militar N; moistur R; revital N; romantic; summar N; sermon; solemn N; empath; eulog;
euthan; evangel; overemphas; computer N; containeri; criminal N; dehumani;
demoral; deregular N; destabil N; economi; editorial; humani; iconi; politic N; templat
"""

# Stems in the list above that end in "i" were typed without the trailing "se" by
# mistake-proof convention; they are normalised below.

OUR_WORDS = """
colour colours coloured colouring colourful colourless colourfully
behaviour behaviours behavioural behaviourally
favour favours favoured favouring favourable favourably favourite favourites unfavourable
honour honours honoured honouring honourable dishonour honourably
labour labours laboured labouring labourer labourers
neighbour neighbours neighbouring neighbourhood neighbourhoods
rumour rumours rumoured humour humours humoured
harbour harbours harboured harbouring flavour flavours flavoured flavouring
endeavour endeavours endeavoured endeavouring vapour vapours
savour savoured savouring savoury armour armoured odour odours rigour vigour
tumour tumours valour splendour parlour clamour candour ardour demeanour saviour
"""

PAIRS_OTHER = """
centre center; centres centers; centred centered; centring centering; epicentre epicenter
centimetre centimeter; centimetres centimeters; millimetre millimeter; millimetres millimeters
kilometre kilometer; kilometres kilometers; litre liter; litres liters
fibre fiber; fibres fibers; theatre theater; theatres theaters; calibre caliber
sombre somber; spectre specter; lustre luster; meagre meager; sabre saber
manoeuvre maneuver; manoeuvres maneuvers; manoeuvred maneuvered
catalogue catalog; catalogues catalogs; catalogued cataloged; cataloguing cataloging
analogue analog; analogues analogs
defence defense; defences defenses; offence offense; offences offenses; pretence pretense
analyse analyze; analysed analyzed; analysing analyzing; analyser analyzer; analysers analyzers
paralyse paralyze; paralysed paralyzed; catalyse catalyze; catalysed catalyzed
hydrolyse hydrolyze; electrolyse electrolyze; dialyse dialyze
travelled traveled; travelling traveling; traveller traveler; travellers travelers
modelled modeled; modelling modeling; modeller modeler; modellers modelers
labelled labeled; labelling labeling; cancelled canceled; cancelling canceling
signalled signaled; signalling signaling; levelled leveled; levelling leveling
fuelled fueled; fuelling fueling; channelled channeled; channelling channeling
totalled totaled; totalling totaling; counselling counseling; counsellor counselor
counsellors counselors; marshalled marshaled; tunnelled tunneled; tunnelling tunneling
quarrelled quarreled; jewellery jewelry; woollen woolen
enrolment enrollment; enrolments enrollments; fulfil fulfill; fulfils fulfills
fulfilment fulfillment; skilful skillful; skilfully skillfully; wilful willful
instalment installment; instalments installments; distil distill; instil instill
grey gray; aluminium aluminum; mould mold; moulds molds; moulded molded; moulding molding
plough plow; ageing aging; acknowledgement acknowledgment; acknowledgements acknowledgments
judgement judgment; judgements judgments; artefact artifact; artefacts artifacts
sceptical skeptical; sceptic skeptic; scepticism skepticism; paediatric pediatric
encyclopaedia encyclopedia; anaemia anemia; haemoglobin hemoglobin; oestrogen estrogen
orthopaedic orthopedic; foetus fetus; pyjamas pajamas; cosy cozy; sulphur sulfur
"""


def _ise_pairs() -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for item in ISE_STEMS.replace("\n", " ").split(";"):
        parts = item.split()
        if not parts:
            continue
        stem, flags = parts[0], parts[1] if len(parts) > 1 else ""
        stem = stem[:-1] if stem.endswith("i") else stem  # "optimi" -> "optim"
        endings = ["ise", "ised", "ises", "ising"]
        if "N" in flags:
            endings += ["isation", "isations"]
        if "R" in flags:
            endings += ["iser", "isers"]
        for ending in endings:
            pairs.append((stem + ending, stem + ending.replace("is", "iz", 1)))
    return pairs


def _our_pairs() -> list[tuple[str, str]]:
    return [(word, word.replace("our", "or", 1)) for word in OUR_WORDS.split()]


def _other_pairs() -> list[tuple[str, str]]:
    pairs = []
    for item in PAIRS_OTHER.replace("\n", ";").split(";"):
        parts = item.split()
        if len(parts) == 2:
            pairs.append((parts[0], parts[1]))
    return pairs


def build() -> list[tuple[str, str, str]]:
    rows: dict[str, tuple[str, str, str]] = {}
    for uk, us in _ise_pairs():
        rows[uk] = (uk, us, "ize")
    for uk, us in _our_pairs() + _other_pairs():
        rows[uk] = (uk, us, "other")
    return sorted(rows.values())


def render() -> str:
    header = "# UK\tUS\tgroup — generated by tools/make_spelling_pairs.py; do not edit\n"
    return header + "".join(f"{uk}\t{us}\t{group}\n" for uk, us, group in build())


if __name__ == "__main__":
    OUT.write_text(render(), encoding="utf-8")
    print(f"wrote {len(build())} pairs to {OUT}")
