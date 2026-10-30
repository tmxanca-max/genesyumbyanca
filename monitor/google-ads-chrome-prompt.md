# Prompt pentru raportul Google Ads (Claude în Chrome, luni dimineața)

Folosește Claude în Chrome, cu browserul logat în contul MCC. Nu modifica nimic în conturi, doar citește.

---

Deschide Google Ads, contul MCC (managerul), pagina „Conturi" / „Accounts". Setează intervalul la ultimele 7 zile.

Pentru fiecare cont de client din listă, notează: nume cont, cost, clickuri, conversii, valoarea conversiilor, ROAS (valoare conversii / cost), CPC mediu.
Dacă un cont nu are cheltuială în ultimele 7 zile, scrie „fără reclame active".

Pentru conturile cu cheltuială mai mare de 0, intră în cont și verifică:
- campaniile active și bugetul zilnic;
- Search terms ale ultimelor 7 zile: termenii cu cost și zero conversii (primii 5);
- avertismente sau campanii limitate / respinse / cont suspendat.

Reguli:
- 🔴 cheltuit 50 sau mai mult cu zero conversii, cont suspendat, produse respinse în masă;
- 🟠 ROAS sub break-even (2.0 dacă nu am dat altă valoare);
- 🟢 ROAS peste break-even.

Răspunde în română, un bloc scurt pe cursant (cifre + semafor + o recomandare concretă), apoi o listă cu primele 3 priorități pentru mine.
Dacă apare CAPTCHA, verificare prin SMS sau cere parolă, oprește-te și spune-mi, nu încerca să o ocolești.
