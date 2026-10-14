// buat-mado.mjs — membuat model chibi Mado, Putri Peri dari Taman Bulan, untuk Badai Shinobi.
//
// Menghasilkan assets/petarung/mado.gltf.json (P1) dan mado-p2.gltf.json (kostum kedua).
// Rangka 15 tulang dan klip animasi (siaga, kuda_kuda, jalan, pukul) disalin dari bayu.gltf.json
// supaya Mado bergerak persis seperti petarung lain. Tubuhnya disusun dari bentuk dasar, setiap
// bagian diikat ke tulangnya. Material memakai nama yang dikenali js/petarung.js:
// kain, kulit, rambut (diberi garis tinta), cahaya (tanpa bayangan) dan sayap (tembus pandang).
//
// Jalankan dari akar repo:  node tools/buat-mado.mjs

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
const PALET = {
  p1: { kulit: '#f6d2b8', pipi: '#ff9cb4', rambut: '#f5c6e0', rambutGelap: '#e3a6cc', gaun: '#fdf6ff', gaunBayang: '#e9def7', aksen: '#b9a2f0', aksenTua: '#9781d8', list: '#e8c05a', emas: '#e8c05a', sepatu: '#d9a945', stoking: '#f7f1ff', permata: '#fff3a8',
    sayapDalam: '#e8fbff', sayapTepi: '#bfe9ff', sayapUjung: '#d9c9ff', sayapUrat: '#a9dcff',
    putih: '#ffffff', iris: '#7a5cff', irisAtas: '#4a2fcc', irisBawah: '#b8a2ff', pupil: '#24145a', bulu: '#2a1a3a', mulut: '#c24f6c' },
  p2: { kulit: '#f6d2b8', pipi: '#ff9cb4', rambut: '#f5c6e0', rambutGelap: '#e3a6cc', gaun: '#2d2a4a', gaunBayang: '#221f3a', aksen: '#d8dce6', aksenTua: '#aab0c0', list: '#d8dce6', emas: '#e8c05a', sepatu: '#d9a945', stoking: '#eceaf4', permata: '#fff3a8',
    sayapDalam: '#fff2fa', sayapTepi: '#ffd6f0', sayapUjung: '#f1c6ff', sayapUrat: '#ffbfe6',
    putih: '#ffffff', iris: '#7a5cff', irisAtas: '#4a2fcc', irisBawah: '#b8a2ff', pupil: '#24145a', bulu: '#2a1a3a', mulut: '#c24f6c' },
};

// ---------- pembantu geometri ----------
const UP = new THREE.Vector3(0, 1, 0), FWD = new THREE.Vector3(0, 0, 1);
const ss = (a, b, x) => { const t = Math.min(1, Math.max(0, (x - a) / (b - a))); return t * t * (3 - 2 * t); };
const V = (x, y, z) => new THREE.Vector3(x, y, z);
const C = w => new THREE.Color(w);
const campur = (a, b, t) => C(a).lerp(C(b), t);
const rad = THREE.MathUtils.degToRad;
// pekatkan warna (ruang linear): k > 1 menjauhkan dari abu-abu, g < 1 menggelapkan
const jenuh = (w, k, g) => { const c = C(w), l = .2126 * c.r + .7152 * c.g + .0722 * c.b; return new THREE.Color(l * g + (c.r - l) * k, l * g + (c.g - l) * k, l * g + (c.b - l) * k); };
const tr = (g, { s, r, q, p }) => { const m = new THREE.Matrix4(); m.compose(p || V(0, 0, 0), q || (r ? new THREE.Quaternion().setFromEuler(new THREE.Euler(...r)) : new THREE.Quaternion()), s ? (typeof s === 'number' ? V(s, s, s) : V(...s)) : V(1, 1, 1)); return g.applyMatrix4(m); };
// tabung dari titik a (jari-jari ra) ke titik b (jari-jari rb)
function limb(a, b, ra, rb, seg = 16) {
  const d = new THREE.Vector3().subVectors(a, b), L = d.length();
  return tr(new THREE.CylinderGeometry(ra, rb, L, seg, 2), { q: new THREE.Quaternion().setFromUnitVectors(UP, d.normalize()), p: a.clone().add(b).multiplyScalar(.5) });
}
// kerucut dengan pangkal di p, mengarah ke dir
function cone(p, dir, r, h, seg = 8) { return tr(new THREE.ConeGeometry(r, h, seg).translate(0, h / 2, 0), { q: new THREE.Quaternion().setFromUnitVectors(UP, dir.clone().normalize()), p }); }
const ball = (p, s, seg = 16) => tr(new THREE.SphereGeometry(1, seg, Math.max(8, seg * .75 | 0)), { s, p });
// geometri berindeks dari daftar verteks dan segitiga
function geoDari(pos, idx, warna) {
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  if (warna) g.setAttribute('color', new THREE.Float32BufferAttribute(warna, 3));
  g.setIndex(idx); g.computeVertexNormals(); return g;
}
// bintang empat sudut berfaset (permata cahaya), menghadap +Z
function bintang(r, tebal = .4, sudut = 4) {
  const pos = [0, 0, r * tebal, 0, 0, -r * tebal], idx = [], n = sudut * 2;
  for (let i = 0; i < n; i++) { const a = i / n * Math.PI * 2 + Math.PI / 2, k = i % 2 ? .38 : 1; pos.push(Math.cos(a) * r * k, Math.sin(a) * r * k, 0); }
  for (let i = 0; i < n; i++) { const a = 2 + i, b = 2 + (i + 1) % n; idx.push(0, a, b, 1, b, a); }
  return geoDari(pos, idx);
}
// rok bubut berlipit: jari-jari berombak menurut sudut, makin dalam ke bawah
function bubutLipit(profil, lipit, amp, pipih, seg = 64) {
  const g = new THREE.LatheGeometry(profil.map(([r, y]) => new THREE.Vector2(r, y)), seg), p = g.attributes.position, y0 = profil[0][1], y1 = profil[profil.length - 1][1];
  for (let i = 0; i < p.count; i++) {
    const x = p.getX(i), y = p.getY(i), z = p.getZ(i), f = 1 + amp * ss(y0, y1, y) * Math.sin(lipit * Math.atan2(x, z));
    p.setXYZ(i, x * f, y, z * f * pipih);
  }
  g.computeVertexNormals(); return g;
}
// garis kelim yang mengikuti ombak rok
function kelim(r, y, lipit, amp, pipih, tebal) {
  const titik = []; for (let i = 0; i < 96; i++) { const a = i / 96 * Math.PI * 2, f = r * (1 + amp * Math.sin(lipit * a)); titik.push(V(Math.sin(a) * f, y, Math.cos(a) * f * pipih)); }
  return new THREE.TubeGeometry(new THREE.CatmullRomCurve3(titik, true), 128, tebal, 6, true);
}
// helai rambut pipih: disapu sepanjang kurva, lebar mengecil ke ujung; acuan(p) = arah "keluar" helai
function helai(titik, lebar, tebal, acuan, warnaLuar, warnaDalam, { n = 18, m = 8, pangkal = .75, ujung = 1 } = {}) {
  const kurva = new THREE.CatmullRomCurve3(titik, false, 'centripetal'), pos = [], col = [], huv = [], idx = [];
  const cL = C(warnaLuar), cD = C(warnaDalam), c = new THREE.Color();
  for (let i = 0; i <= n; i++) {
    const t = i / n, p = kurva.getPointAt(t), T = kurva.getTangentAt(t);
    const Bw = new THREE.Vector3().crossVectors(T, acuan(p)).normalize(), N = new THREE.Vector3().crossVectors(Bw, T).normalize();
    const w = lebar * (pangkal + (1 - pangkal) * Math.sin(Math.min(1, t / .4) * Math.PI / 2)) * (1 - ujung * ss(.45, 1, t) ** 1.3) + .002;
    const d = tebal * (1 - .7 * ss(.6, 1, t));
    for (let k = 0; k < m; k++) {
      const a = k / m * Math.PI * 2, ca = Math.cos(a), sa = Math.sin(a);
      pos.push(p.x + Bw.x * ca * w + N.x * sa * d, p.y + Bw.y * ca * w + N.y * sa * d, p.z + Bw.z * ca * w + N.z * sa * d);
      c.copy(cD).lerp(cL, ss(-.6, .5, sa)); col.push(c.r, c.g, c.b);
      huv.push(t, (ca + 1) / 2);
    }
  }
  for (let i = 0; i < n; i++) for (let k = 0; k < m; k++) { const a = i * m + k, b = i * m + (k + 1) % m, a2 = a + m, b2 = b + m; idx.push(a, a2, b, b, a2, b2); }
  const g = geoDari(pos, idx, col); g.setAttribute('huv', new THREE.Float32BufferAttribute(huv, 2)); return g;
}
// sayap peri: kipas dari pangkal ke garis tepi (bentuk dari THREE.Shape), warna memudar dari pangkal ke tepi
function sayapPeri(bentuk, P, { pangkal, sudut, sapu, lengkung = .06, cincin = 6 }, sx) {
  const tepi = bentuk.getSpacedPoints(64); tepi.pop();
  const L = Math.max(...tepi.map(p => p.x)), q = new THREE.Quaternion().setFromEuler(new THREE.Euler(0, sapu, sudut, 'YXZ'));
  const pos = [], col = [], idx = [], c = new THREE.Color(), cD = C(P.sayapDalam), cT = C(P.sayapTepi), cU = C(P.sayapUjung), cV = C(P.sayapUrat);
  const titik = (u, v, s, urat) => {
    const p = V(u, v, -lengkung * (u / L) ** 2 - lengkung * .5 * (v / L) ** 2).applyQuaternion(q);
    pos.push(pangkal.x + sx * p.x, pangkal.y + p.y, pangkal.z + p.z);
    c.copy(cD).lerp(cT, ss(.15, 1, s)).lerp(cU, ss(.55, 1, u / L) * .55 * s); if (urat) c.lerp(cV, .5 * ss(.2, .6, s)); if (s > .96) c.lerp(cV, .6);
    col.push(c.r, c.g, c.b);
  };
  titik(0, 0, 0, false);
  for (let j = 1; j <= cincin; j++) { const s = j / cincin; tepi.forEach((p, i) => titik(p.x * s, p.y * s, s, i % 8 === 4)); }
  const n = tepi.length;
  for (let i = 0; i < n; i++) idx.push(0, 1 + i, 1 + (i + 1) % n);
  for (let j = 1; j < cincin; j++) for (let i = 0; i < n; i++) { const a = 1 + (j - 1) * n + i, b = 1 + (j - 1) * n + (i + 1) % n; idx.push(a, a + n, b, b, a + n, b + n); }
  return geoDari(pos, idx, col);
}
function bentukSayap(L, W, atas) {
  const s = new THREE.Shape(); s.moveTo(0, 0);
  if (atas) { s.bezierCurveTo(.18 * L, .5 * W, .58 * L, .72 * W, .9 * L, .5 * W); s.bezierCurveTo(1.05 * L, .38 * W, 1.05 * L, -.08 * W, .86 * L, -.16 * W); s.bezierCurveTo(.58 * L, -.28 * W, .24 * L, -.2 * W, 0, 0); }
  else { s.bezierCurveTo(.2 * L, .32 * W, .6 * L, .5 * W, .9 * L, .3 * W); s.bezierCurveTo(1.06 * L, .18 * W, 1.02 * L, -.26 * W, .78 * L, -.3 * W); s.bezierCurveTo(.5 * L, -.34 * W, .2 * L, -.18 * W, 0, 0); }
  return s;
}

// ---------- kepala: elips, dan titik-titik di permukaannya ----------
const HC = V(0, 1.68, 0), HR = V(.46, .48, .40);
function permukaan(x, y, keluar = 0) {
  const k = 1 - (x / HR.x) ** 2 - ((y - HC.y) / HR.y) ** 2, z = HR.z * Math.sqrt(Math.max(0, k));
  const n = V(x / HR.x ** 2, (y - HC.y) / HR.y ** 2, z / HR.z ** 2).normalize();
  return { p: V(x, y, z).addScaledVector(n, keluar), n };
}
// tempelan datar di wajah (mata, mulut): bentuk dibuat menghadap +Z lalu diputar ke normal kulit
function tempel(g, x, y, keluar, putarZ = 0) {
  const { p, n } = permukaan(x, y, keluar);
  const q = new THREE.Quaternion().setFromUnitVectors(FWD, n).multiply(new THREE.Quaternion().setFromAxisAngle(FWD, putarZ));
  return tr(g, { q, p });
}
// tudung rambut: elips sedikit lebih besar dari kepala, dimiringkan supaya tepi depannya naik
const RC = V(0, 1.7, -.02), RR = V(.49, .51, .44), RMIRING = -.12;
const qRambut = new THREE.Quaternion().setFromEuler(new THREE.Euler(RMIRING, 0, 0));
// titik di permukaan tudung pada azimut az (0 = depan, + ke kiri karakter) dan elevasi el (derajat)
function diRambut(az, el, keluar = 0) {
  const a = rad(az), e = rad(el), d = V(Math.sin(a) * Math.cos(e), Math.sin(e), Math.cos(a) * Math.cos(e));
  return V(d.x * (RR.x + keluar), d.y * (RR.y + keluar), d.z * (RR.z + keluar)).applyQuaternion(qRambut).add(RC);
}

// badan (korset gaun): profil bubut, sedikit pipih ke depan
const BADAN = [[.212, .6], [.206, .7], [.214, .8], [.222, .826], [.224, .844], [.236, .95], [.228, 1.06], [.19, 1.14], [.11, 1.19]];
const PIPIH = .82;
function jariBadan(y) { for (let i = 1; i < BADAN.length; i++) if (y <= BADAN[i][1]) { const [r0, y0] = BADAN[i - 1], [r1, y1] = BADAN[i]; return r0 + (r1 - r0) * (y - y0) / (y1 - y0); } return BADAN[BADAN.length - 1][0]; }
const depanBadan = (x, y, keluar = .012) => PIPIH * Math.sqrt(Math.max(0, jariBadan(y) ** 2 - x * x)) + keluar;

// ---------- ikatan kulit ke tulang ----------
const kaku = j => () => [[j, 1]];
const sambung = (bawah, atas, y0, pita) => v => { const w = ss(y0 - pita, y0 + pita, v.y); return [[atas, w], [bawah, 1 - w]]; };
const ikatBadan = v => { const wd = ss(.84, .98, v.y), wp = 1 - ss(.62, .76, v.y); return [['dada', wd], ['perut', Math.max(0, 1 - wd - wp)], ['pinggul', wp]]; };
// rambut panjang: kepala di atas, dada di bawah tengkuk
const ikatRambut = sambung('dada', 'kepala', 1.3, .14);
// rok: pinggul, bagian bawahnya sedikit ikut paha supaya kaki tidak menembus saat melangkah
const ikatRok = v => { const t = .42 * ss(.6, .34, v.y), ki = t * ss(-.08, .14, v.x), ka = t * ss(-.08, .14, -v.x); return [['pinggul', 1 - ki - ka], ['pahaKi', ki], ['pahaKa', ka]]; };

function bangun(P) {
  const bagian = { kain: [], kulit: [], rambut: [], cahaya: [], sayap: [] };
  // warna: string, fungsi (posisi) -> warna, atau null bila geometri sudah membawa warna sendiri
  function add(mat, g, warna, ikat) {
    if (g.attributes.uv) g.deleteAttribute('uv');
    if (g.attributes.uv1) g.deleteAttribute('uv1');
    if (mat === 'rambut' && !g.attributes.huv) g.setAttribute('huv', new THREE.BufferAttribute(new Float32Array(g.attributes.position.count * 2), 2));
    if (mat !== 'rambut' && g.attributes.huv) g.deleteAttribute('huv');
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
    bagian[mat].push(g);
  }

  // kepala dengan rona pipi, leher
  const pipi = [-1, 1].map(sx => V(sx * .255, 1.465, 0));
  add('kulit', ball(HC, [HR.x, HR.y, HR.z], 56), v => {
    let t = 0; for (const p of pipi) t = Math.max(t, Math.exp(-(((v.x - p.x) / .085) ** 2 + ((v.y - p.y) / .05) ** 2)));
    return campur(P.kulit, P.pipi, v.z > 0 ? .78 * t : 0);
  }, kaku('kepala'));
  add('kulit', limb(V(0, 1.27, -.01), V(0, 1.1, -.01), .075, .085), P.kulit, sambung('dada', 'kepala', 1.2, .04));

  // korset gaun: putih di atas, pita lavender dari pinggang sampai bawah dada, list emas
  add('kain', tr(new THREE.LatheGeometry(BADAN.map(([r, y]) => new THREE.Vector2(r, y)), 40), { s: [1, 1, PIPIH] }), v => C(v.y < .835 ? P.aksen : P.gaun), ikatBadan);
  for (const [y, r, t] of [[.835, jariBadan(.835) + .004, .012], [1.165, .16, .016]]) add('kain', tr(new THREE.TorusGeometry(r, t, 6, 40), { r: [Math.PI / 2, 0, 0], s: [1, PIPIH, 1], p: V(0, y, 0) }), P.list, ikatBadan);
  // tali silang emas di depan korset
  for (const sx of [1, -1]) {
    const titik = [[.07, .82], [-.05, .74], [.05, .67]].map(([x, y]) => V(x * sx, y, depanBadan(x * sx, y, .006)));
    add('kain', new THREE.TubeGeometry(new THREE.CatmullRomCurve3(titik), 16, .008, 5), P.list, ikatBadan);
  }
  // kerah kelopak bunga dan bros bintang cahaya
  for (const az of [-38, 38, -100, 100, 180]) {
    const a = rad(az), r = .17, p = V(Math.sin(a) * r, 1.148, Math.cos(a) * r * PIPIH);
    add('kain', tr(new THREE.SphereGeometry(1, 16, 10), { s: [.085, .02, .07], q: new THREE.Quaternion().setFromEuler(new THREE.Euler(.42, a, 0, 'YXZ')), p }), P.aksen, kaku('dada'));
  }
  add('kain', tr(new THREE.TorusGeometry(.034, .009, 6, 20), { p: V(0, 1.09, depanBadan(0, 1.09, .01)) }), P.emas, kaku('dada'));
  add('cahaya', tr(bintang(.042), { p: V(0, 1.09, depanBadan(0, 1.09, .016)) }), P.permata, kaku('dada'));

  // selempang lavender di pinggang, pita besar di punggung
  add('kain', tr(new THREE.TorusGeometry(jariBadan(.66) + .012, .03, 10, 44), { r: [Math.PI / 2, 0, 0], s: [1, PIPIH, 1], p: V(0, .66, 0) }), P.aksen, kaku('pinggul'));
  const zBelakang = -depanBadan(0, .66, .04);
  for (const sx of [-1, 1]) {
    add('kain', tr(new THREE.TorusGeometry(.052, .022, 8, 20), { s: [1.3, .8, .55], r: [0, sx * .25, sx * .2], p: V(sx * .072, .68, zBelakang - .01) }), P.aksen, kaku('pinggul'));
    add('kain', tr(new THREE.BoxGeometry(.05, .2, .012), { r: [.28, 0, sx * .18], p: V(sx * .04, .55, zBelakang - .04) }), P.aksen, kaku('pinggul'));
  }
  add('kain', ball(V(0, .665, zBelakang), [.035, .032, .025], 12), P.aksenTua, kaku('pinggul'));

  // rok mengembang dua lapis berlipit: lapis bawah lavender lebih panjang, lapis atas putih dengan kelim emas
  const RB = [[.22, .67], [.25, .6], [.305, .52], [.365, .43], [.405, .35]], RA = [[.226, .68], [.265, .61], [.33, .52], [.392, .43]];
  add('kain', bubutLipit(RB, 18, .055, .86), P.aksen, ikatRok);
  add('kain', kelim(.405, .35, 18, .055, .86, .012), P.list, ikatRok);
  add('kain', bubutLipit(RA, 14, .06, .86), v => campur(P.gaun, P.gaunBayang, ss(.55, .43, v.y) * .5), ikatRok);
  add('kain', kelim(.392, .43, 14, .06, .86, .016), P.list, ikatRok);

  // lengan: lengan baju menggembung, lengan kurus, gelang emas
  for (const [s, sx] of [['Ki', 1], ['Ka', -1]]) {
    const bahu = B['lenganAtas' + s], siku = B['lenganBawah' + s], tangan = B['tangan' + s], arah = tangan.clone().sub(siku).normalize(), arahAtas = siku.clone().sub(bahu).normalize();
    add('kulit', limb(bahu.clone().add(V(0, .02, 0)), siku, .056, .05), P.kulit, kaku('lenganAtas' + s));
    add('kulit', limb(siku, tangan, .049, .043), P.kulit, kaku('lenganBawah' + s));
    add('kulit', ball(tangan.clone().addScaledVector(arah, .045), [.06, .068, .056]), P.kulit, kaku('tangan' + s));
    add('kulit', ball(tangan.clone().addScaledVector(arah, .02).add(V(-sx * .01, 0, .05)), [.022, .032, .022], 10), P.kulit, kaku('tangan' + s));
    const pusatG = bahu.clone().addScaledVector(arahAtas, .06).add(V(sx * .015, 0, 0)), qG = new THREE.Quaternion().setFromUnitVectors(UP, arahAtas);
    const gembung = tr(new THREE.SphereGeometry(1, 24, 14), { s: [.108, .095, .104] }), gp = gembung.attributes.position;
    for (let i = 0; i < gp.count; i++) { const x = gp.getX(i), z = gp.getZ(i), f = 1 + .07 * Math.sin(10 * Math.atan2(x, z)) * (1 - Math.abs(gp.getY(i)) / .095); gp.setX(i, x * f); gp.setZ(i, z * f); }
    gembung.computeVertexNormals();
    add('kain', tr(gembung, { q: qG, p: pusatG }), v => campur(P.gaun, P.gaunBayang, ss(.02, -.07, v.clone().sub(pusatG).dot(arahAtas) * -1) * .6), kaku('lenganAtas' + s));
    add('kain', tr(new THREE.TorusGeometry(.062, .013, 6, 24), { q: new THREE.Quaternion().setFromUnitVectors(FWD, arahAtas), p: pusatG.clone().addScaledVector(arahAtas, .078) }), P.list, kaku('lenganAtas' + s));
    add('kain', tr(new THREE.TorusGeometry(.05, .011, 6, 20), { q: new THREE.Quaternion().setFromUnitVectors(FWD, arah), p: siku.clone().lerp(tangan, .9) }), P.emas, kaku('lenganBawah' + s));
  }

  // kaki: stoking terang dan sepatu bot kecil emas
  for (const s of ['Ki', 'Ka']) {
    const paha = B['paha' + s], lutut = B['betis' + s], x = paha.x;
    add('kain', limb(paha.clone().add(V(0, .03, 0)), lutut, .084, .07), P.stoking, kaku('paha' + s));
    add('kain', limb(lutut.clone().add(V(0, .02, 0)), V(x, .1, 0), .068, .056), P.stoking, kaku('betis' + s));
    add('kain', limb(V(x, .19, 0), V(x, .06, .005), .06, .057), P.sepatu, kaku('betis' + s));
    add('kain', tr(new THREE.TorusGeometry(.062, .012, 6, 24), { r: [Math.PI / 2, 0, 0], p: V(x, .19, 0) }), P.list, kaku('betis' + s));
    add('kain', ball(V(x, .046, .035), [.064, .046, .108]), P.sepatu, kaku('betis' + s));
    add('cahaya', tr(bintang(.018, .5), { p: V(x, .13, .062) }), P.permata, kaku('betis' + s));
  }

  // warna rambut di model dibuat sedikit lebih pekat dari warna nominal supaya tidak pudar jadi putih di bawah lampu arena
  const rambutModel = jenuh(P.rambut, 1.45, .9);
  // rambut: tudung, isi bagian belakang (warna bayang), tirai panjang sampai pinggang, poni, dua helai samping
  const tudung = new THREE.SphereGeometry(1, 56, 22, 0, Math.PI * 2, 0, Math.PI * .5), tp = tudung.attributes.position;
  for (let i = 0; i < tp.count; i++) {
    const x = tp.getX(i), y = tp.getY(i), z = tp.getZ(i), f = Math.atan2(x, z), depan = Math.max(0, Math.cos(f)) ** 2;
    const th = Math.acos(Math.min(1, y)) / (Math.PI / 2) * (Math.PI / 2 - rad(26) * depan);
    tp.setXYZ(i, Math.sin(th) * Math.sin(f), Math.cos(th), Math.sin(th) * Math.cos(f));
  }
  tudung.computeVertexNormals();
  // koordinat serat untuk tudung: garis-garis halus memancar dari ubun-ubun
  const thu = new Float32Array(tp.count * 2); for (let i = 0; i < tp.count; i++) { thu[i * 2] = 1 - tp.getY(i); thu[i * 2 + 1] = (Math.atan2(tp.getX(i), tp.getZ(i)) / Math.PI + 1) * 5; }
  tudung.setAttribute('huv', new THREE.BufferAttribute(thu, 2));
  add('rambut', tr(tudung, { s: [RR.x, RR.y, RR.z], q: qRambut, p: RC }), v => campur(rambutModel, P.rambutGelap, .25 - .25 * ss(2.0, 2.2, v.y)), kaku('kepala'));
  add('rambut', tr(new THREE.SphereGeometry(1, 40, 18, Math.PI * 1.5 - 2.25, 4.5, Math.PI * .46, Math.PI * .38), { s: [RR.x - .006, RR.y - .006, RR.z - .006], q: qRambut, p: RC }), P.rambutGelap, kaku('kepala'));
  // tirai belakang: panel bayang di dalam, helai-helai di luarnya
  const keluarSumbu = p => V(p.x, 0, p.z + .04).normalize(), rambutHelai = campur(rambutModel, P.rambutGelap, .2);
  const jalurTirai = (az, r, yUjung) => {
    const a = rad(az), h = (y, rr) => V(Math.sin(a) * rr, y, Math.cos(a) * rr * .92 - .03);
    return [diRambut(az, 46, -.03), diRambut(az, 20, .012), diRambut(az, 2, .03), diRambut(az, -28, .045), h(1.24, r + .015), h(1.0, r), h(.82, r - .01), h(yUjung, r - .03)];
  };
  for (let az = 128; az <= 232; az += 13) add('rambut', helai(jalurTirai(az, .3, .78), .12, .02, keluarSumbu, P.rambutGelap, P.rambutGelap, { pangkal: 1, ujung: .6 }), null, ikatRambut);
  [[180, .7, .17, 0], [154, .72, .16, .012], [206, .72, .16, .012], [130, .78, .14, 0], [230, .78, .14, 0], [167, .68, .14, .024], [193, .68, .14, .024], [142, .75, .13, .02], [218, .75, .13, .02]]
    .forEach(([az, yU, w, dk]) => add('rambut', helai(jalurTirai(az, .33 + dk, yU), w, .03, keluarSumbu, rambutHelai, P.rambutGelap), null, ikatRambut));
  // helai sisi kepala yang menutup telinga dan jatuh di belakang bahu
  for (const sx of [-1, 1]) for (const [az, yU] of [[98, 1.3], [114, 1.08]]) {
    const a = rad(az * sx);
    const jalur = [diRambut(az * sx, 40, -.03), diRambut(az * sx, 18, .012), diRambut(az * sx, 0, .03), diRambut(az * sx, -30, .03), V(Math.sin(a) * .36, 1.3, Math.cos(a) * .36 - .02), V(Math.sin(a) * .37, yU, Math.cos(a) * .4 - .04)];
    add('rambut', helai(jalur, .13, .03, keluarSumbu, rambutHelai, P.rambutGelap), null, ikatRambut);
  }
  // poni lembut di dahi: helai dari ubun-ubun menyisir ke depan, ujungnya berhenti di atas mata
  const keluarKepala = p => p.clone().sub(RC).normalize();
  for (const [az, yUjung, w, geser] of [[0, 1.74, .13, -6], [-17, 1.725, .13, -4], [17, 1.73, .12, -7], [-34, 1.71, .12, -2], [33, 1.715, .12, -4], [-52, 1.66, .12, 4], [51, 1.665, .12, -2], [8, 1.75, .09, 6], [-26, 1.74, .09, 0]]) {
    const jalur = []; for (const [t, el, k] of [[0, 72, -.03], [.2, 60, .012], [.45, 44, .022], [.7, 30, .03], [.9, 18, .036]]) jalur.push(diRambut(az + geser * t, el, k));
    const pU = permukaan(Math.sin(rad(az + geser)) * .4 * Math.min(1, 1.1 - Math.abs(az) / 200), yUjung, .035).p;
    jalur.push(pU);
    add('rambut', helai(jalur, w, .028, keluarKepala, rambutHelai, P.rambutGelap, { pangkal: .9 }), null, kaku('kepala'));
  }
  // dua helai samping yang membingkai wajah sampai ke dada
  for (const sx of [-1, 1]) {
    const jalur = [diRambut(sx * 60, 34, -.03), diRambut(sx * 64, 18, .015), diRambut(sx * 74, -8, .045), V(sx * .43, 1.42, .17), V(sx * .37, 1.22, .16), V(sx * .3, 1.05, .19), V(sx * .27, .93, .2)];
    add('rambut', helai(jalur, .075, .03, p => V(sx, 0, .6).normalize(), rambutHelai, P.rambutGelap, { pangkal: 1, n: 22 }), null, ikatRambut);
  }

  // mahkota kecil emas tiga runcing dengan permata cahaya, duduk di puncak kepala
  const pM = diRambut(0, 74, -.005), qM = new THREE.Quaternion().setFromEuler(new THREE.Euler(-.26 + RMIRING, 0, 0)), rM = .135;
  const diMahkota = (x, y, z) => V(x, y, z).applyQuaternion(qM).add(pM);
  add('kain', tr(new THREE.CylinderGeometry(rM, rM * .94, .05, 40, 1, true), { q: qM, p: diMahkota(0, .01, 0) }), P.emas, kaku('kepala'));
  for (const y of [-.015, .035]) add('kain', tr(new THREE.TorusGeometry(rM + (y < 0 ? -.006 : 0), .008, 6, 40), { q: qM.clone().multiply(new THREE.Quaternion().setFromEuler(new THREE.Euler(Math.PI / 2, 0, 0))), p: diMahkota(0, y, 0) }), P.emas, kaku('kepala'));
  for (const [az, h] of [[0, .12], [-38, .085], [38, .085], [180, .07], [-110, .06], [110, .06]]) {
    const a = rad(az), dasar = diMahkota(Math.sin(a) * rM, .03, Math.cos(a) * rM), atas = diMahkota(Math.sin(a) * rM * 1.02, .03 + h, Math.cos(a) * rM * 1.02);
    add('kain', cone(dasar, atas.clone().sub(dasar), .028, h, 8), P.emas, kaku('kepala'));
    add('cahaya', ball(atas.clone().add(V(0, .008, 0)), .014, 10), P.permata, kaku('kepala'));
  }
  add('cahaya', tr(bintang(.034, .5), { q: qM, p: diMahkota(0, .012, rM + .008) }), P.permata, kaku('kepala'));

  // wajah: mata besar ungu (pupil bulat, dua kilau, bulu mata atas), mulut senyum kecil
  const yMata = 1.565;
  for (const sx of [-1, 1]) {
    const x = sx * .165;
    add('cahaya', tempel(new THREE.SphereGeometry(1, 20, 12).scale(.084, .106, .012), x, yMata, .004), P.putih, kaku('kepala'));
    add('cahaya', tempel(new THREE.SphereGeometry(1, 24, 14).scale(.07, .092, .012), x, yMata - .01, .009), v => campur(P.irisAtas, P.irisBawah, ss(yMata + .06, yMata - .09, v.y)), kaku('kepala'));
    add('cahaya', tempel(new THREE.SphereGeometry(1, 16, 10).scale(.034, .042, .012), x, yMata - .012, .014), P.pupil, kaku('kepala'));
    add('cahaya', tempel(new THREE.SphereGeometry(1, 12, 8).scale(.025, .029, .012), x - sx * .022, yMata + .028, .02), P.putih, kaku('kepala'));
    add('cahaya', tempel(new THREE.SphereGeometry(1, 10, 6).scale(.012, .012, .012), x + sx * .024, yMata - .042, .02), P.putih, kaku('kepala'));
    const busur = Math.PI * .78;
    add('cahaya', tempel(new THREE.TorusGeometry(.094, .011, 5, 20, busur).rotateZ((Math.PI - busur) / 2 + sx * .05).scale(.97, 1.08, .5), x, yMata + .004, .016), P.bulu, kaku('kepala'));
    add('cahaya', tempel(new THREE.BoxGeometry(.05, .016, .01), x + sx * .1, yMata + .055, .016, sx * .55), P.bulu, kaku('kepala'));
  }
  add('cahaya', tempel(new THREE.TorusGeometry(.034, .0075, 5, 14, Math.PI * .7).rotateZ(Math.PI + Math.PI * .15), 0, 1.43, .008), P.mulut, kaku('kepala'));

  // dua pasang sayap peri di punggung
  for (const sx of [-1, 1]) {
    add('sayap', sayapPeri(bentukSayap(.95, .56, true), P, { pangkal: V(sx * .05, 1.0, -.17), sudut: .72, sapu: .55 }, sx), null, kaku('dada'));
    add('sayap', sayapPeri(bentukSayap(.6, .42, false), P, { pangkal: V(sx * .05, .9, -.16), sudut: -.55, sapu: .5 }, sx), null, kaku('dada'));
  }

  return Object.fromEntries(Object.entries(bagian).map(([k, list]) => [k, mergeGeometries(list)]));
}

// ---------- tulis glTF ----------
function tulis(varian) {
  const P = PALET[varian], mesh = bangun(P);
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

  const info = { id: 'mado', nama: 'Mado', julukan: 'Putri Peri dari Taman Bulan', asal: 'Taman Bulan', senjata: 'Panah seribu cahaya', elemen: 'Cahaya', varian, warna: P, skala: .72, tinggiMeter: 1.78, klip: src.animations.map(a => a.name) };
  const nodes = RIG.map(n => Object.fromEntries(Object.entries(n).filter(([k]) => ['name', 'translation', 'rotation', 'children'].includes(k))));
  const iAkar = RIG.findIndex(n => n.name === 'akar'), nm = ['body', 'kulit', 'rambut', 'glow', 'sayap'];
  const iMesh = meshes.map((m, i) => nodes.push({ name: 'mado_' + nm[i], mesh: i, skin: 0 }) - 1);
  const iWadah = nodes.push({ name: 'mado', scale: [.72, .72, .72], extras: info, children: [iAkar, ...iMesh] }) - 1;
  const iPuncak = nodes.push({ name: 'petarung_mado', extras: info, children: [iWadah] }) - 1;
  const bin = Buffer.concat(chunks);
  const gltf = { asset: { version: '2.0', generator: 'Badai Shinobi tools/buat-mado.mjs' }, scene: 0, scenes: [{ name: 'AuxScene', nodes: [iPuncak] }], nodes, meshes, materials: MATS, skins: [{ inverseBindMatrices: ibmAcc, joints: skinJoints, skeleton: iAkar }], animations, accessors, bufferViews, buffers: [{ byteLength: bin.length, uri: 'data:application/octet-stream;base64,' + bin.toString('base64') }] };
  const out = join(ROOT, 'assets/petarung', varian === 'p1' ? 'mado.gltf.json' : 'mado-p2.gltf.json');
  writeFileSync(out, JSON.stringify(gltf));
  console.log(out, (bin.length / 1024).toFixed(0) + ' KB', Object.fromEntries(MATS.map(m => [m.name, mesh[m.name].attributes.position.count])));
}
tulis('p1'); tulis('p2');
