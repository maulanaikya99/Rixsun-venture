// buat-marko.mjs — membuat model chibi Marko, Ninja Gravitasi, untuk Badai Shinobi.
//
// Menghasilkan assets/petarung/marko.gltf.json (P1) dan marko-p2.gltf.json (kostum kedua).
// Rangka 15 tulang dan klip animasi (siaga, kuda_kuda, jalan, pukul) disalin dari bayu.gltf.json
// supaya Marko bergerak persis seperti petarung lain. Tubuhnya disusun dari bentuk dasar, setiap
// bagian diikat ke tulangnya. Material memakai nama yang dikenali js/petarung.js:
// kain, kulit, rambut (diberi garis tinta), cahaya (garis neon, tanpa bayangan) dan sayap (syal energi tembus pandang).
//
// Penampilan: setelan ninja modern futuristik. Baju ketat gelap, pelat zirah abu baja, garis neon biru,
// inti gravitasi di dada, masker wajah bawah, ikat kepala berpelat dengan visor, cincin gravitasi di punggung.
//
// Jalankan dari akar repo:  node tools/buat-marko.mjs

import * as THREE from '../lib/three/three.module.js';
import { mergeGeometries } from '../lib/three/addons/utils/BufferGeometryUtils.js';
import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const src = JSON.parse(readFileSync(join(ROOT, 'assets/petarung/bayu.gltf.json'), 'utf8'));
const srcBuf = Buffer.from(src.buffers[0].uri.slice(src.buffers[0].uri.indexOf(',') + 1), 'base64');

// ---------- rangka (disalin) ----------
const RIG = src.nodes.slice(0, 15);
const skinJoints = src.skins[0].joints;
const objs = RIG.map(n => { const o = new THREE.Object3D(); o.name = n.name; if (n.translation) o.position.fromArray(n.translation); if (n.rotation) o.quaternion.fromArray(n.rotation); return o; });
RIG.forEach((n, i) => (n.children || []).forEach(c => objs[i].add(objs[c])));
const akar = objs.find(o => o.name === 'akar'); akar.updateMatrixWorld(true);
const B = {}; for (const o of objs) B[o.name] = o.getWorldPosition(new THREE.Vector3());
const JI = {}; skinJoints.forEach((ni, k) => { JI[RIG[ni].name] = k; });

// ---------- palet ----------
// P1: setelan hitam kebiruan, zirah baja, neon biru. P2: setelan putih, zirah perak, neon merah.
const PALET = {
  p1: { kulit: '#e6b58c', setelan: '#1b2133', setelanTua: '#121725', zirah: '#4a566e', zirahTua: '#323b4f', perak: '#aab6cc', neon: '#3ab8ff', neonMuda: '#bdf0ff', inti: '#e8fbff',
    rambut: '#161b29', ujungRambut: '#2f7dff', masker: '#202838', syal: '#3ab8ff', syalTepi: '#9fe6ff', syalUjung: '#2f6bff',
    putih: '#f6f9ff', iris: '#33b4ff', irisAtas: '#1a5fd6', pupil: '#0a1a3a', garis: '#141826' },
  p2: { kulit: '#e6b58c', setelan: '#e4e9f1', setelanTua: '#c4ccd8', zirah: '#8f99ab', zirahTua: '#6b7487', perak: '#2b3142', neon: '#ff4a6a', neonMuda: '#ffc2cc', inti: '#fff0f2',
    rambut: '#161b29', ujungRambut: '#e0334f', masker: '#2b3142', syal: '#ff4a6a', syalTepi: '#ffb0bd', syalUjung: '#d61f45',
    putih: '#f6f9ff', iris: '#ff5a76', irisAtas: '#b5173a', pupil: '#2a0812', garis: '#141826' },
};

// ---------- pembantu geometri ----------
const UP = new THREE.Vector3(0, 1, 0), FWD = new THREE.Vector3(0, 0, 1);
const ss = (a, b, x) => { const t = Math.min(1, Math.max(0, (x - a) / (b - a))); return t * t * (3 - 2 * t); };
const V = (x, y, z) => new THREE.Vector3(x, y, z);
const C = w => new THREE.Color(w);
const campur = (a, b, t) => C(a).lerp(C(b), t);
const rad = THREE.MathUtils.degToRad;
const tr = (g, { s, r, q, p }) => { const m = new THREE.Matrix4(); m.compose(p || V(0, 0, 0), q || (r ? new THREE.Quaternion().setFromEuler(new THREE.Euler(...r)) : new THREE.Quaternion()), s ? (typeof s === 'number' ? V(s, s, s) : V(...s)) : V(1, 1, 1)); return g.applyMatrix4(m); };
// tabung dari titik a (jari-jari ra) ke titik b (jari-jari rb)
function limb(a, b, ra, rb, seg = 16) {
  const d = new THREE.Vector3().subVectors(a, b), L = d.length();
  return tr(new THREE.CylinderGeometry(ra, rb, L, seg, 2), { q: new THREE.Quaternion().setFromUnitVectors(UP, d.normalize()), p: a.clone().add(b).multiplyScalar(.5) });
}
// kerucut dengan pangkal di p, mengarah ke dir
function cone(p, dir, r, h, seg = 8) { return tr(new THREE.ConeGeometry(r, h, seg).translate(0, h / 2, 0), { q: new THREE.Quaternion().setFromUnitVectors(UP, dir.clone().normalize()), p }); }
const ball = (p, s, seg = 16) => tr(new THREE.SphereGeometry(1, seg, Math.max(8, seg * .75 | 0)), { s, p });
// cincin tegak lurus terhadap sumbu
const cincin = (p, sumbu, r, t, seg = 24) => tr(new THREE.TorusGeometry(r, t, 6, seg), { q: new THREE.Quaternion().setFromUnitVectors(FWD, sumbu.clone().normalize()), p });
// garis neon tipis yang mengikuti titik-titik
const neon = (titik, t = .007, seg = 16) => new THREE.TubeGeometry(new THREE.CatmullRomCurve3(titik), seg, t, 5);
function geoDari(pos, idx, warna) {
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  if (warna) g.setAttribute('color', new THREE.Float32BufferAttribute(warna, 3));
  g.setIndex(idx); g.computeVertexNormals(); return g;
}
// pita pipih (syal energi): disapu sepanjang kurva, warna memudar dari pangkal ke ujung
function pita(titik, lebar, acuan, P, n = 22) {
  const kurva = new THREE.CatmullRomCurve3(titik, false, 'centripetal'), pos = [], col = [], idx = [], c = new THREE.Color();
  for (let i = 0; i <= n; i++) {
    const t = i / n, p = kurva.getPointAt(t), T = kurva.getTangentAt(t), Bw = new THREE.Vector3().crossVectors(T, acuan).normalize();
    const w = lebar * (1 - .55 * t);
    for (const k of [-1, 0, 1]) {
      pos.push(p.x + Bw.x * w * k, p.y + Bw.y * w * k, p.z + Bw.z * w * k);
      c.copy(C(P.syal)).lerp(C(P.syalUjung), ss(.2, 1, t)); if (k) c.lerp(C(P.syalTepi), .55); col.push(c.r, c.g, c.b);
    }
  }
  for (let i = 0; i < n; i++) for (let k = 0; k < 2; k++) { const a = i * 3 + k, b = a + 1, a2 = a + 3, b2 = b + 3; idx.push(a, a2, b, b, a2, b2); }
  return geoDari(pos, idx, col);
}

// ---------- kepala: elips, dan titik-titik di permukaannya ----------
const HC = V(0, 1.68, 0), HR = V(.46, .48, .40);
function permukaan(x, y, keluar = 0) {
  const k = 1 - (x / HR.x) ** 2 - ((y - HC.y) / HR.y) ** 2, z = HR.z * Math.sqrt(Math.max(0, k));
  const n = V(x / HR.x ** 2, (y - HC.y) / HR.y ** 2, z / HR.z ** 2).normalize();
  return { p: V(x, y, z).addScaledVector(n, keluar), n };
}
// tempelan datar di wajah (mata, alis): bentuk dibuat menghadap +Z lalu diputar ke normal kulit
function tempel(g, x, y, keluar, putarZ = 0) {
  const { p, n } = permukaan(x, y, keluar);
  const q = new THREE.Quaternion().setFromUnitVectors(FWD, n).multiply(new THREE.Quaternion().setFromAxisAngle(FWD, putarZ));
  return tr(g, { q, p });
}

// badan: profil bubut (jari-jari terhadap tinggi), sedikit pipih ke depan; dada sedikit lebih bidang
const BADAN = [[.262, .42], [.255, .55], [.236, .70], [.246, .86], [.268, .98], [.258, 1.08], [.205, 1.15], [.12, 1.19]];
const PIPIH = .8;
function jariBadan(y) { for (let i = 1; i < BADAN.length; i++) if (y <= BADAN[i][1]) { const [r0, y0] = BADAN[i - 1], [r1, y1] = BADAN[i]; return r0 + (r1 - r0) * (y - y0) / (y1 - y0); } return BADAN[BADAN.length - 1][0]; }
const depanBadan = (x, y, keluar = .012) => PIPIH * Math.sqrt(Math.max(0, jariBadan(y) ** 2 - x * x)) + keluar;

// ---------- ikatan kulit ke tulang ----------
const kaku = j => () => [[j, 1]];
const sambung = (bawah, atas, y0, pita) => v => { const w = ss(y0 - pita, y0 + pita, v.y); return [[atas, w], [bawah, 1 - w]]; };
const ikatBadan = v => { const wd = ss(.84, .98, v.y), wp = 1 - ss(.62, .76, v.y); return [['dada', wd], ['perut', Math.max(0, 1 - wd - wp)], ['pinggul', wp]]; };

function bangun(P) {
  const bagian = { kain: [], kulit: [], rambut: [], cahaya: [], sayap: [] };
  // warna: string, fungsi (posisi) -> warna, atau null bila geometri sudah membawa warna sendiri
  function add(mat, g, warna, ikat) {
    if (g.attributes.uv) g.deleteAttribute('uv');
    if (g.attributes.uv1) g.deleteAttribute('uv1');
    if (g.attributes.normal === undefined) g.computeVertexNormals();
    if (mat === 'rambut' && !g.attributes.huv) g.setAttribute('huv', new THREE.BufferAttribute(new Float32Array(g.attributes.position.count * 2), 2));
    const pos = g.attributes.position, n = pos.count, c = new THREE.Color();
    const col = warna === null ? g.attributes.color.array : new Float32Array(n * 3), si = new Uint16Array(n * 4), sw = new Float32Array(n * 4), v = new THREE.Vector3();
    if (typeof warna === 'string') c.set(warna);
    for (let i = 0; i < n; i++) {
      v.fromBufferAttribute(pos, i);
      if (typeof warna === 'function') c.copy(warna(v));
      if (warna !== null) { col[i * 3] = c.r; col[i * 3 + 1] = c.g; col[i * 3 + 2] = c.b; }
      const ws = ikat(v).filter(w => w[1] > 1e-4).sort((a, b) => b[1] - a[1]).slice(0, 4), tot = ws.reduce((s, w) => s + w[1], 0);
      ws.forEach(([j, w], k) => { si[i * 4 + k] = JI[j]; sw[i * 4 + k] = w / tot; });
    }
    g.setAttribute('color', new THREE.BufferAttribute(col, 3));
    g.setAttribute('skinIndex', new THREE.BufferAttribute(si, 4));
    g.setAttribute('skinWeight', new THREE.BufferAttribute(sw, 4));
    bagian[mat].push(g.index ? g : g.setIndex([...Array(n).keys()]));
  }

  // kepala, leher (tertutup kerah setelan)
  add('kulit', ball(HC, [HR.x, HR.y, HR.z], 48), P.kulit, kaku('kepala'));
  add('kain', limb(V(0, 1.3, -.01), V(0, 1.1, -.01), .1, .11), P.setelanTua, sambung('dada', 'kepala', 1.2, .04));

  // masker ninja: cangkang menutup hidung sampai dagu, dengan garis neon dan dua kisi napas
  const RM = V(HR.x + .022, HR.y + .022, HR.z + .03);
  const masker = new THREE.SphereGeometry(1, 40, 14, Math.PI / 2 - 1.45, 2.9, 2.03, .92);
  add('kain', tr(masker, { s: [RM.x, RM.y, RM.z], p: HC }), v => campur(P.masker, P.setelanTua, ss(1.4, 1.25, v.y) * .6), kaku('kepala'));
  const yGaris = 1.445, kG = Math.sqrt(Math.max(0, 1 - ((yGaris - HC.y) / RM.y) ** 2));
  const garisMasker = []; for (let i = 0; i <= 20; i++) { const a = rad(-70 + i * 7); garisMasker.push(V(Math.sin(a) * RM.x * kG * 1.01, yGaris - Math.abs(Math.sin(a)) * .03, Math.cos(a) * RM.z * kG * 1.01)); }
  add('cahaya', neon(garisMasker, .0075, 40), P.neon, kaku('kepala'));
  for (const sx of [-1, 1]) for (const dy of [0, .028, .056]) {
    const y = 1.39 - dy, kk = Math.sqrt(Math.max(0, 1 - ((y - HC.y) / RM.y) ** 2)), a = rad(sx * 24);
    add('kain', tr(new THREE.BoxGeometry(.07, .011, .012), { r: [0, a, 0], p: V(Math.sin(a) * RM.x * kk * 1.01, y, Math.cos(a) * RM.z * kk * 1.01) }), P.zirahTua, kaku('kepala'));
  }

  // setelan ketat dengan panel samping lebih gelap
  add('kain', tr(new THREE.LatheGeometry(BADAN.map(([r, y]) => new THREE.Vector2(r, y)), 40), { s: [1, 1, PIPIH] }), v => campur(P.setelan, P.setelanTua, ss(.55, .9, Math.abs(v.x) / jariBadan(v.y)) * .8), ikatBadan);
  // zirah dada: cangkang melengkung di depan, kerah tinggi
  const ZD = [[jariBadan(.82) + .03, .82], [jariBadan(.95) + .035, .95], [jariBadan(1.06) + .03, 1.06], [jariBadan(1.13) + .02, 1.13]];
  const zirahDada = new THREE.LatheGeometry(ZD.map(([r, y]) => new THREE.Vector2(r, y)), 36, -1.25, 2.5);
  add('kain', tr(zirahDada, { s: [1, 1, PIPIH] }), v => campur(P.zirah, P.zirahTua, ss(.95, .82, v.y) * .5), ikatBadan);
  add('kain', tr(new THREE.CylinderGeometry(.13, .15, .1, 28, 1, true), { p: V(0, 1.19, -.005) }), P.zirahTua, sambung('dada', 'kepala', 1.2, .04));
  add('cahaya', cincin(V(0, 1.24, -.005), UP, .13, .006, 28), P.neon, sambung('dada', 'kepala', 1.2, .04));
  // inti gravitasi di tengah dada: cincin baja, cahaya inti, dua cincin orbit kecil
  const pInti = V(0, .97, depanBadan(0, .97, .045));
  add('kain', cincin(pInti, FWD, .06, .017, 28), P.perak, kaku('dada'));
  add('cahaya', tr(new THREE.SphereGeometry(.045, 16, 10), { s: [1, 1, .5], p: pInti }), P.inti, kaku('dada'));
  add('cahaya', cincin(pInti.clone().add(V(0, 0, .006)), V(.35, .2, 1), .085, .0055, 30), P.neon, kaku('dada'));
  add('cahaya', cincin(pInti.clone().add(V(0, 0, .006)), V(-.35, .2, 1), .085, .0055, 30), P.neon, kaku('dada'));
  // garis neon di zirah dada dan perut
  for (const sx of [-1, 1]) {
    add('cahaya', neon([[.2, 1.1], [.16, 1.0], [.12, .9], [.07, .84]].map(([x, y]) => V(x * sx, y, depanBadan(x * sx, y, .042)))), P.neon, ikatBadan);
    add('cahaya', neon([[.15, .8], [.17, .72], [.16, .64]].map(([x, y]) => V(x * sx, y, depanBadan(x * sx, y, .006)))), P.neon, ikatBadan);
  }
  // sabuk teknologi dengan gesper bercahaya dan kantong di pinggul
  add('kain', tr(new THREE.TorusGeometry(.252, .034, 8, 40), { r: [Math.PI / 2, 0, 0], s: [1, PIPIH, 1], p: V(0, .64, 0) }), P.zirahTua, kaku('pinggul'));
  add('kain', tr(new THREE.BoxGeometry(.12, .075, .03), { p: V(0, .64, depanBadan(0, .64, .028)) }), P.perak, kaku('pinggul'));
  add('cahaya', tr(new THREE.BoxGeometry(.07, .018, .01), { p: V(0, .64, depanBadan(0, .64, .046)) }), P.neon, kaku('pinggul'));
  for (const sx of [-1, 1]) add('kain', tr(new THREE.BoxGeometry(.08, .1, .07), { r: [0, sx * .9, 0], p: V(sx * .22, .6, .1) }), P.zirah, kaku('pinggul'));
  // rok pelindung pendek berpanel di pinggul
  for (const az of [-150, -110, -60, 60, 110, 150]) {
    const a = rad(az), r = .27, p = V(Math.sin(a) * r, .53, Math.cos(a) * r * .86);
    add('kain', tr(new THREE.BoxGeometry(.13, .17, .02), { q: new THREE.Quaternion().setFromEuler(new THREE.Euler(-.12, a, 0, 'YXZ')), p }), P.zirahTua, kaku('pinggul'));
  }

  // lengan: setelan ketat, pelindung bahu, pelindung lengan bawah bergaris neon, sarung tangan
  for (const [s, sx] of [['Ki', 1], ['Ka', -1]]) {
    const bahu = B['lenganAtas' + s], siku = B['lenganBawah' + s], tangan = B['tangan' + s], arah = tangan.clone().sub(siku).normalize();
    add('kain', limb(bahu.clone().add(V(0, .02, 0)), siku, .07, .06), P.setelan, kaku('lenganAtas' + s));
    add('kain', limb(siku, tangan, .058, .052), P.setelan, kaku('lenganBawah' + s));
    add('kain', ball(tangan.clone().addScaledVector(arah, .045), [.068, .075, .064]), P.setelanTua, kaku('tangan' + s));
    add('kain', ball(tangan.clone().addScaledVector(arah, .02).add(V(-sx * .01, 0, .056)), [.026, .036, .026], 10), P.setelanTua, kaku('tangan' + s));
    add('kain', tr(new THREE.BoxGeometry(.06, .02, .05), { p: tangan.clone().addScaledVector(arah, .03).add(V(sx * .04, 0, 0)) }), P.zirah, kaku('tangan' + s));
    // pelindung lengan bawah
    add('kain', limb(siku.clone().lerp(tangan, .18), siku.clone().lerp(tangan, .92), .074, .066, 8), P.zirah, kaku('lenganBawah' + s));
    add('cahaya', cincin(siku.clone().lerp(tangan, .55), arah, .072, .007), P.neon, kaku('lenganBawah' + s));
    add('cahaya', neon([siku.clone().lerp(tangan, .2).add(V(sx * .05, 0, .05)), siku.clone().lerp(tangan, .88).add(V(sx * .045, 0, .045))], .006, 6), P.neonMuda, kaku('lenganBawah' + s));
    // pelindung bahu bertingkat
    [[.0, .065, .13, P.zirah], [.025, .005, .115, P.zirahTua]].forEach(([dx, dy, r, w], i) => {
      add('kain', tr(new THREE.SphereGeometry(1, 20, 10, 0, Math.PI * 2, 0, Math.PI / 2), { s: [r, r * .7, r * 1.05], r: [0, 0, -sx * (.42 + i * .12)], p: bahu.clone().add(V(sx * dx, dy, 0)) }), w, kaku('lenganAtas' + s));
    });
    add('cahaya', tr(new THREE.TorusGeometry(.128, .0065, 5, 32, Math.PI), { r: [0, Math.PI / 2, -sx * .42 + Math.PI / 2 * 0], p: bahu.clone().add(V(0, .065, 0)) }), P.neon, kaku('lenganAtas' + s));
  }

  // kaki: celana setelan, pelindung lutut, sepatu bot zirah bergaris neon
  for (const s of ['Ki', 'Ka']) {
    const paha = B['paha' + s], lutut = B['betis' + s], x = paha.x;
    add('kain', limb(paha.clone().add(V(0, .03, 0)), lutut, .096, .08), P.setelan, kaku('paha' + s));
    add('kain', limb(lutut.clone().add(V(0, .02, 0)), V(x, .12, 0), .078, .066), P.setelan, kaku('betis' + s));
    add('kain', ball(lutut.clone().add(V(0, .01, .06)), [.07, .075, .045], 12), P.zirah, kaku('betis' + s));
    add('cahaya', tr(new THREE.BoxGeometry(.05, .012, .01), { p: lutut.clone().add(V(0, .01, .106)) }), P.neon, kaku('betis' + s));
    add('kain', limb(V(x, .24, 0), V(x, .07, .005), .078, .085, 12), P.zirah, kaku('betis' + s));
    add('kain', ball(V(x, .055, .05), [.088, .058, .14]), P.zirahTua, kaku('betis' + s));
    add('cahaya', cincin(V(x, .2, 0), UP, .08, .006), P.neon, kaku('betis' + s));
    add('cahaya', tr(new THREE.BoxGeometry(.012, .1, .01), { p: V(x, .15, .085) }), P.neonMuda, kaku('betis' + s));
  }

  // ikat kepala modern: pita setelan, pelat baja dengan lambang gravitasi neon, dua ujung pita di belakang
  const yIkat = 1.75, kIkat = Math.sqrt(1 - ((yIkat - HC.y) / HR.y) ** 2);
  add('kain', tr(new THREE.CylinderGeometry(1, 1, .075, 44, 1, true), { s: [HR.x * kIkat + .014, 1, HR.z * kIkat + .014], p: V(0, yIkat, 0) }), P.setelanTua, kaku('kepala'));
  add('kain', tempel(new THREE.BoxGeometry(.2, .085, .022), 0, yIkat, .024), P.perak, kaku('kepala'));
  add('cahaya', tempel(new THREE.TorusGeometry(.024, .0055, 5, 20), 0, yIkat, .038), P.neon, kaku('kepala'));
  add('cahaya', tempel(tr(new THREE.TorusGeometry(.044, .004, 4, 28), { s: [1, .38, 1] }), 0, yIkat, .038, -.3), P.neon, kaku('kepala'));
  add('cahaya', tempel(new THREE.SphereGeometry(.011, 8, 6), 0, yIkat, .04), P.inti, kaku('kepala'));
  for (const sx of [-1, 1]) add('kain', tr(new THREE.BoxGeometry(.05, .3, .012), { r: [.4, 0, sx * .16], p: V(sx * .05, yIkat - .14, -HR.z * kIkat - .05) }), P.setelanTua, kaku('kepala'));
  // penutup telinga teknologi, antena di sisi kiri
  for (const sx of [-1, 1]) {
    add('kain', tr(new THREE.CylinderGeometry(.072, .078, .07, 20), { r: [0, 0, Math.PI / 2], p: V(sx * .45, 1.6, -.01) }), P.zirah, kaku('kepala'));
    add('cahaya', cincin(V(sx * .487, 1.6, -.01), V(1, 0, 0), .048, .007), P.neon, kaku('kepala'));
  }
  add('kain', limb(V(.48, 1.64, -.04), V(.56, 1.95, -.16), .011, .007, 6), P.perak, kaku('kepala'));
  add('cahaya', ball(V(.56, 1.95, -.16), .018, 8), P.neon, kaku('kepala'));

  // rambut: tudung di atas ikat kepala dan jambul runcing tersibak ke atas-belakang; ujung helai biru neon
  const RC = V(0, 1.8, -.03), RR = V(.47, .46, .43);
  const warnaRambut = v => campur(P.rambut, P.ujungRambut, ss(.62, .84, v.clone().sub(RC).length()) * .8);
  add('rambut', tr(new THREE.SphereGeometry(1, 40, 20, 0, Math.PI * 2, 0, Math.PI * .5), { s: [RR.x, RR.y, RR.z], p: RC }), P.rambut, kaku('kepala'));
  add('rambut', tr(new THREE.SphereGeometry(1, 36, 18, Math.PI - .4, Math.PI + .8, Math.PI * .3, Math.PI * .55), { s: [.5, .52, .46], p: V(0, 1.7, -.03) }), P.rambut, kaku('kepala'));
  const sisirBelakang = V(0, .55, -1).normalize();
  // [azimut, elevasi, jari-jari, panjang, condong ke belakang]
  for (const [az, el, r, h, k] of [
    [0, 40, .13, .46, .45], [24, 44, .12, .42, .5], [-24, 44, .12, .42, .5], [0, 66, .14, .5, .6], [-12, 58, .11, .44, .5],
    [52, 34, .12, .4, .62], [-52, 34, .12, .4, .62], [88, 26, .11, .38, .72], [-88, 26, .11, .38, .72],
    [124, 28, .11, .42, .8], [-124, 28, .11, .42, .8], [158, 38, .12, .46, .85], [-158, 38, .12, .46, .85],
    [180, 58, .13, .48, .85], [146, 64, .12, .44, .8], [-146, 64, .12, .44, .8], [98, 54, .11, .4, .72], [-98, 54, .11, .4, .72], [180, 18, .1, .38, .9]]) {
    const a = rad(az), e = rad(el);
    const keluar = V(Math.sin(a) * Math.cos(e), Math.sin(e), Math.cos(a) * Math.cos(e));
    const p = V(RC.x + keluar.x * RR.x * .8, RC.y + keluar.y * RR.y * .8, RC.z + keluar.z * RR.z * .8);
    add('rambut', cone(p, keluar.clone().multiplyScalar(1 - k).addScaledVector(sisirBelakang, k).add(V(0, .3, 0)), r, h, 7), warnaRambut, kaku('kepala'));
  }
  // dua helai poni tajam jatuh di atas ikat kepala, cambang pendek
  for (const [x, dx, h] of [[-.14, -.3, .22], [.08, .2, .17], [-.02, -.05, .14]]) add('rambut', cone(V(x, 1.9, .34), V(dx, -1, .55), .045, h, 6), warnaRambut, kaku('kepala'));
  for (const sx of [-1, 1]) add('rambut', cone(V(sx * .41, 1.8, .14), V(sx * .05, -1, .2), .06, .2, 7), P.rambut, kaku('kepala'));

  // wajah: mata tajam biru menyala (pupil tegas, kilau), kelopak atas tebal, alis miring tegas
  const yMata = 1.565;
  for (const sx of [-1, 1]) {
    const x = sx * .158;
    add('cahaya', tempel(new THREE.SphereGeometry(1, 20, 12).scale(.08, .084, .012), x, yMata, .004), P.putih, kaku('kepala'));
    add('cahaya', tempel(new THREE.SphereGeometry(1, 20, 12).scale(.06, .07, .012), x - sx * .004, yMata - .006, .009), v => campur(P.irisAtas, P.iris, ss(yMata + .05, yMata - .05, v.y)), kaku('kepala'));
    add('cahaya', tempel(new THREE.SphereGeometry(1, 14, 10).scale(.026, .036, .012), x - sx * .004, yMata - .006, .014), P.pupil, kaku('kepala'));
    add('cahaya', tempel(new THREE.SphereGeometry(1, 10, 8).scale(.018, .02, .012), x - .02, yMata + .022, .019), P.putih, kaku('kepala'));
    add('cahaya', tempel(new THREE.SphereGeometry(1, 8, 6).scale(.009, .009, .012), x + .02, yMata - .034, .019), P.putih, kaku('kepala'));
    // kelopak atas tebal
    add('cahaya', tempel(new THREE.BoxGeometry(.18, .028, .012), x + sx * .008, yMata + .07, .014, -sx * .2), P.garis, kaku('kepala'));
    add('cahaya', tempel(new THREE.BoxGeometry(.13, .028, .012), sx * .15, 1.672, .012, sx * .3), P.rambut, kaku('kepala'));
  }

  // syal energi tembus pandang: lilitan di leher dan dua ekor yang berkibar ke belakang
  add('kain', tr(new THREE.TorusGeometry(.135, .045, 10, 28), { r: [Math.PI / 2, 0, 0], s: [1, .9, 1], p: V(0, 1.16, -.01) }), P.setelanTua, kaku('dada'));
  add('cahaya', tr(new THREE.TorusGeometry(.135, .008, 5, 28), { r: [Math.PI / 2, 0, 0], s: [1, .9, 1], p: V(0, 1.2, -.01) }), P.neon, kaku('dada'));
  for (const [sx, panjang] of [[1, 1], [-1, .85]]) {
    const titik = [V(sx * .05, 1.15, -.15), V(sx * .12, 1.06, -.3), V(sx * .2, .92, -.46), V(sx * .28, .76 + (1 - panjang) * .2, -.6), V(sx * .36, .58 + (1 - panjang) * .3, -.7), V(sx * .42, .44 + (1 - panjang) * .35, -.76)];
    add('sayap', pita(titik, .075, V(0, 1, .4).normalize(), P), null, kaku('dada'));
  }

  // cincin gravitasi di punggung: lingkar baja bercahaya, tiga bola orbit
  const pCincin = V(0, .98, -depanBadan(0, .98, .12));
  add('kain', limb(V(0, .98, -depanBadan(0, .98, -.02)), pCincin, .03, .03, 8), P.zirahTua, kaku('dada'));
  add('kain', cincin(pCincin, V(0, 0, 1), .25, .018, 40), P.zirah, kaku('dada'));
  add('cahaya', cincin(pCincin.clone().add(V(0, 0, -.012)), V(0, 0, 1), .25, .009, 40), P.neon, kaku('dada'));
  add('cahaya', tr(new THREE.SphereGeometry(.035, 12, 8), { p: pCincin.clone().add(V(0, 0, -.01)) }), P.inti, kaku('dada'));
  for (const a of [rad(90), rad(210), rad(330)]) add('cahaya', ball(pCincin.clone().add(V(Math.cos(a) * .25, Math.sin(a) * .25, -.015)), .026, 10), P.neonMuda, kaku('dada'));

  // samakan atribut supaya semua potongan bisa digabung
  const rapikan = (k, g) => { for (const a of Object.keys(g.attributes)) if (!['position', 'normal', 'color', 'skinIndex', 'skinWeight', ...(k === 'rambut' ? ['huv'] : [])].includes(a)) g.deleteAttribute(a); return g; };
  return Object.fromEntries(Object.entries(bagian).map(([k, list]) => [k, mergeGeometries(list.map(g => rapikan(k, g)))]));
}

// ---------- tulis glTF ----------
function tulis(varian) {
  const P = PALET[varian], mesh = bangun(P);
  for (const [k, g] of Object.entries(mesh)) if (!g) throw new Error('Gagal menggabungkan geometri ' + k);
  const chunks = []; let len = 0;
  const bufferViews = [], accessors = [];
  function data(typed, target) {
    const pad = (4 - len % 4) % 4; if (pad) { chunks.push(Buffer.alloc(pad)); len += pad; }
    const b = Buffer.from(typed.buffer, typed.byteOffset, typed.byteLength);
    bufferViews.push(Object.assign({ buffer: 0, byteOffset: len, byteLength: b.length }, target ? { target } : {}));
    chunks.push(b); len += b.length; return bufferViews.length - 1;
  }
  const N = { SCALAR: 1, VEC2: 2, VEC3: 3, VEC4: 4, MAT4: 16 };
  function acc(typed, type, componentType, target, minmax) {
    const a = { bufferView: data(typed, target), componentType, count: typed.length / N[type], type };
    if (minmax) { const n = N[type], mn = Array(n).fill(Infinity), mx = Array(n).fill(-Infinity); for (let i = 0; i < typed.length; i++) { const k = i % n; mn[k] = Math.min(mn[k], typed[i]); mx[k] = Math.max(mx[k], typed[i]); } a.min = mn; a.max = mx; }
    accessors.push(a); return accessors.length - 1;
  }
  const MATS = [
    { name: 'kain', pbrMetallicRoughness: { metallicFactor: 0, roughnessFactor: .86 } },
    { name: 'kulit', pbrMetallicRoughness: { metallicFactor: 0, roughnessFactor: .5 } },
    { name: 'rambut', pbrMetallicRoughness: { metallicFactor: 0, roughnessFactor: .44 } },
    { name: 'cahaya', pbrMetallicRoughness: { metallicFactor: 0, roughnessFactor: 1 }, emissiveFactor: [1, 1, 1] },
    { name: 'sayap', pbrMetallicRoughness: { baseColorFactor: [1, 1, 1, .7], metallicFactor: 0, roughnessFactor: 1 }, alphaMode: 'BLEND', doubleSided: true },
  ];
  const meshes = MATS.map((m, mi) => {
    const g = mesh[m.name], a = g.attributes, idx = g.index.array;
    const big = a.position.count > 65535;
    const attributes = {
      POSITION: acc(new Float32Array(a.position.array), 'VEC3', 5126, 34962, true),
      NORMAL: acc(new Float32Array(a.normal.array), 'VEC3', 5126, 34962),
      COLOR_0: acc(new Float32Array(a.color.array), 'VEC3', 5126, 34962),
      JOINTS_0: acc(new Uint16Array(a.skinIndex.array), 'VEC4', 5123, 34962),
      WEIGHTS_0: acc(new Float32Array(a.skinWeight.array), 'VEC4', 5126, 34962),
    };
    // koordinat helai rambut untuk pola serat di material rambut (dibaca js/petarung.js sebagai huv)
    if (a.huv) attributes._HUV = acc(new Float32Array(a.huv.array), 'VEC2', 5126, 34962);
    return { primitives: [{ mode: 4, material: mi, indices: acc(big ? new Uint32Array(idx) : new Uint16Array(idx), 'SCALAR', big ? 5125 : 5123, 34963), attributes }] };
  });
  const ibm = new Float32Array(skinJoints.length * 16);
  skinJoints.forEach((ni, k) => ibm.set(objs[ni].matrixWorld.clone().invert().elements, k * 16));
  const ibmAcc = acc(ibm, 'MAT4', 5126);
  // klip animasi disalin apa adanya; target node 0–14 tetap sama
  const salin = ai => { const a = src.accessors[ai], bv = src.bufferViews[a.bufferView], off = (bv.byteOffset || 0) + (a.byteOffset || 0); return new Float32Array(srcBuf.buffer.slice(srcBuf.byteOffset + off, srcBuf.byteOffset + off + a.count * N[a.type] * 4)); };
  const animations = src.animations.map(an => ({ name: an.name, channels: an.channels, samplers: an.samplers.map(s => ({ interpolation: s.interpolation, input: acc(salin(s.input), 'SCALAR', 5126, undefined, true), output: acc(salin(s.output), src.accessors[s.output].type, 5126) })) }));

  const info = { id: 'marko', nama: 'Marko', julukan: 'Ninja Gravitasi', asal: 'Kota Orbit', senjata: 'Bayangan pikap api biru', elemen: 'Gravitasi', varian, warna: P, skala: .72, tinggiMeter: 1.78, klip: src.animations.map(a => a.name) };
  const nodes = RIG.map(n => Object.fromEntries(Object.entries(n).filter(([k]) => ['name', 'translation', 'rotation', 'children'].includes(k))));
  const iAkar = RIG.findIndex(n => n.name === 'akar'), nm = ['body', 'kulit', 'rambut', 'glow', 'syal'];
  const iMesh = meshes.map((m, i) => nodes.push({ name: 'marko_' + nm[i], mesh: i, skin: 0 }) - 1);
  const iWadah = nodes.push({ name: 'marko', scale: [.72, .72, .72], extras: info, children: [iAkar, ...iMesh] }) - 1;
  const iPuncak = nodes.push({ name: 'petarung_marko', extras: info, children: [iWadah] }) - 1;
  const bin = Buffer.concat(chunks);
  const gltf = { asset: { version: '2.0', generator: 'Badai Shinobi tools/buat-marko.mjs' }, scene: 0, scenes: [{ name: 'AuxScene', nodes: [iPuncak] }], nodes, meshes, materials: MATS, skins: [{ inverseBindMatrices: ibmAcc, joints: skinJoints, skeleton: iAkar }], animations, accessors, bufferViews, buffers: [{ byteLength: bin.length, uri: 'data:application/octet-stream;base64,' + bin.toString('base64') }] };
  const out = join(ROOT, 'assets/petarung', varian === 'p1' ? 'marko.gltf.json' : 'marko-p2.gltf.json');
  writeFileSync(out, JSON.stringify(gltf));
  console.log(out, (bin.length / 1024).toFixed(0) + ' KB', Object.fromEntries(MATS.map(m => [m.name, mesh[m.name].attributes.position.count])));
}
tulis('p1'); tulis('p2');
