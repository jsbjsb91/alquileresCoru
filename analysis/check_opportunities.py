import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from backend.main import get_properties_df, get_property_by_id

df = get_properties_df()
real_df = df[df["is_real"] == True]

verdicts = {
    "Oportunidad / Muy buen precio": [],
    "Precio de mercado": [],
    "Sobreprecio": []
}

for pid in real_df["id"]:
    det = get_property_by_id(pid)
    v = det.valuation.market_verdict
    if v in verdicts:
        verdicts[v].append((det.title, det.neighborhood, det.price_month, det.valuation.predicted_price, det.valuation.deviation_pct, det.url))

print("================================================================")
print(" 🎯 RADIOGRAFÍA DE ANUNCIOS Y OPORTUNIDADES REALES EN A CORUÑA")
print("================================================================")
print(f"Total anuncios reales analizados: {len(real_df)}")
print(f"🌟 Oportunidades reales detectadas (Chollos): {len(verdicts['Oportunidad / Muy buen precio'])}")
print(f"⚖️ En precio justo de mercado: {len(verdicts['Precio de mercado'])}")
print(f"📈 Sobreprecio respecto a mercado: {len(verdicts['Sobreprecio'])}")

print("\n🌟 TOP OPORTUNIDADES REALES DETECTADAS POR EL MODELO:")
sorted_opps = sorted(verdicts["Oportunidad / Muy buen precio"], key=lambda x: x[4])
for o in sorted_opps[:4]:
    print(f"  * {o[0]} ({o[1]})")
    print(f"    Renta real: {o[2]} €/mes | Valor estimado mercado: {o[3]:.1f} €/mes | Ahorro/Descuento: {abs(o[4]):.1f}%")
    print(f"    🔗 Enlace directo al anuncio: {o[5]}")

print("\n⚠️ ANUNCIOS REALES CON SOBREPRECIO DE MERCADO:")
sorted_over = sorted(verdicts["Sobreprecio"], key=lambda x: x[4], reverse=True)
for ov in sorted_over[:3]:
    print(f"  * {ov[0]} ({ov[1]})")
    print(f"    Renta real: {ov[2]} €/mes | Valor estimado mercado: {ov[3]:.1f} €/mes | Sobreprecio: +{ov[4]:.1f}%")
    print(f"    🔗 Enlace directo al anuncio: {ov[5]}")
