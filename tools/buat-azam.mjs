// buat-azam.mjs — membuat model chibi Azam, Pawang Naga, untuk Badai Shinobi.
//
// Menghasilkan assets/petarung/azam.gltf.json (P1) dan azam-p2.gltf.json (kostum kedua).
// Rangka 15 tulang dan klip animasi (siaga, kuda_kuda, jalan, pukul) disalin dari bayu.gltf.json
// supaya Azam bergerak persis seperti petarung lain. Tubuhnya disusun dari bentuk dasar, setiap
// bagian diikat ke tulangnya. Material memakai nama yang dikenali js/petarung.js:
// kain, kulit, rambut (diberi garis tinta) dan cahaya (tanpa bayangan, untuk mata dan permata).
//
// Jalankan dari akar repo:  node tools/buat-azam.mjs

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
  p1: { kulit: '#d9a77c', rambut: '#16261c', jubah: '#2f7a3a', jubahTua: '#1d4f28', emas: '#d9ac3a', dalam: '#e8e2c8', celana: '#1a2e22', perban: '#d8d2bc', sepatu: '#3a2a1a', syal: '#7cc46a', sisik: '#245c34', sisikTua: '#163d22', ikat: '#1f2a1c', iris: '#e3a21a', pupil: '#2a1408', putih: '#fbf8f0', garis: '#2a1a14', permata: '#66ff88', mulut: '#6a3424' },
  p2: { kulit: '#d9a77c', rambut: '#16261c', jubah: '#5a3a8a', jubahTua: '#3a2560', emas: '#d9ac3a', dalam: '#e8e2c8', celana: '#221a30', perban: '#d8d2bc', sepatu: '#3a2a1a', syal: '#d8dce6', sisik: '#4a2f70', sisikTua: '#2e1d48', ikat: '#241c30', iris: '#e3a21a', pupil: '#2a1408', putih: '#fbf8f0', garis: '#2a1a14', permata: '#c9a0ff', mulut: '#6a3424' },
};

// ---------- pembantu geometri ----------
const UP = new THREE.Vector3(0, 1, 0), FWD = new THREE.Vector3(0, 0, 1);
const ss = (a, b, x) => { const t = Math.min(1, Math.max(0, (x - a) / (b - a))); return t * t * (3 - 2 * t); };
const V = (x, y, z) => new THREE.Vector3(x, y, z);
const tr = (g, { s, r, q, p }) => { const m = new THREE.Matrix4(); m.compose(p || V(0, 0, 0), q || (r ? new THREE.Quaternion().setFromEuler(new THREE.Euler(...r)) : new THREE.Quaternion()), s ? (typeof s === 'number' ? V(s, s, s) : V(...s)) : V(1, 1, 1)); return g.applyMatrix4(m); };
// tabung dari titik a (jari-jari ra) ke titik b (jari-jari rb)
function limb(a, b, ra, rb, seg = 16) {
  const d = new THREE.Vector3().subVectors(a, b), L = d.length();
  return tr(new THREE.CylinderGeometry(ra, rb, L, seg, 2), { q: new THREE.Quaternion().setFromUnitVectors(UP, d.normalize()), p: a.clone().add(b).multiplyScalar(.5) });
}
// kerucut dengan pangkal di p, mengarah ke dir
function cone(p, dir, r, h, seg = 8) { return tr(new THREE.ConeGeometry(r, h, seg).translate(0, h / 2, 0), { q: new THREE.Quaternion().setFromUnitVectors(UP, dir.clone().normalize()), p }); }
const ball = (p, s, seg = 16) => tr(new THREE.SphereGeometry(1, seg, Math.max(8, seg * .75 | 0)), { s, p });

// ---------- kepala: elips, dan titik-titik di permukaannya ----------
const HC = V(0, 1.68, 0), HR = V(.46, .48, .40);
function permukaan(x, y, keluar = 0) {
  const k = 1 - (x / HR.x) ** 2 - ((y - HC.y) / HR.y) ** 2, z = HR.z * Math.sqrt(Math.max(0, k));
  const n = V(x / HR.x ** 2, (y - HC.y) / HR.y ** 2, z / HR.z ** 2).normalize();
  return { p: V(x, y, z).addScaledVector(n, keluar), n };
}
// tempelan datar di wajah (mata, alis, mulut): bentuk dibuat menghadap +Z lalu diputar ke normal kulit
function tempel(g, x, y, keluar, putarZ = 0) {
  const { p, n } = permukaan(x, y, keluar);
  const q = new THREE.Quaternion().setFromUnitVectors(FWD, n).multiply(new THREE.Quaternion().setFromAxisAngle(FWD, putarZ));
  return tr(g, { q, p });
}

// badan: profil bubut (jari-jari terhadap tinggi), sedikit pipih ke depan
const BADAN = [[.27, .42], [.26, .55], [.238, .70], [.245, .86], [.262, .98], [.25, 1.08], [.20, 1.15], [.12, 1.19]];
const PIPIH = .82;
function jariBadan(y) { for (let i = 1; i < BADAN.length; i++) if (y <= BADAN[i][1]) { const [r0, y0] = BADAN[i - 1], [r1, y1] = BADAN[i]; return r0 + (r1 - r0) * (y - y0) / (y1 - y0); } return BADAN[BADAN.length - 1][0]; }
const depanBadan = (x, y, keluar = .012) => PIPIH * Math.sqrt(Math.max(0, jariBadan(y) ** 2 - x * x)) + keluar;

// ---------- ikatan kulit ke tulang ----------
const kaku = j => () => [[j, 1]];
const sambung = (bawah, atas, y0, pita) => v => { const w = ss(y0 - pita, y0 + pita, v.y); return [[atas, w], [bawah, 1 - w]]; };
const ikatBadan = v => { const wd = ss(.84, .98, v.y), wp = 1 - ss(.62, .76, v.y); return [['dada', wd], ['perut', Math.max(0, 1 - wd - wp)], ['pinggul', wp]]; };

function bangun(P) {
  const bagian = { kain: [], kulit: [], rambut: [], cahaya: [] };
  function add(mat, g, warna, ikat) {
    if (g.attributes.uv) g.deleteAttribute('uv');
    if (g.attributes.uv1) g.deleteAttribute('uv1');
    const pos = g.attributes.position, n = pos.count, c = new THREE.Color(warna);
    const col = new Float32Array(n * 3), si = new Uint16Array(n * 4), sw = new Float32Array(n * 4), v = new THREE.Vector3();
    for (let i = 0; i < n; i++) {
      v.fromBufferAttribute(pos, i); col[i * 3] = c.r; col[i * 3 + 1] = c.g; col[i * 3 + 2] = c.b;
      const ws = ikat(v).filter(w => w[1] > 1e-4).sort((a, b) => b[1] - a[1]).slice(0, 4), tot = ws.reduce((s, w) => s + w[1], 0);
      ws.forEach(([j, w], k) => { si[i * 4 + k] = JI[j]; sw[i * 4 + k] = w / tot; });
    }
    g.setAttribute('color', new THREE.BufferAttribute(col, 3));
    g.setAttribute('skinIndex', new THREE.BufferAttribute(si, 4));
    g.setAttribute('skinWeight', new THREE.BufferAttribute(sw, 4));
    bagian[mat].push(g);
  }

  // kepala, telinga, leher
  add('kulit', ball(HC, [HR.x, HR.y, HR.z], 40), P.kulit, kaku('kepala'));
  for (const sx of [-1, 1]) add('kulit', ball(V(sx * .452, 1.6, -.02), [.05, .085, .06], 12), P.kulit, kaku('kepala'));
  add('kulit', limb(V(0, 1.27, -.01), V(0, 1.1, -.01), .085, .095), P.kulit, sambung('dada', 'kepala', 1.2, .04));

  // jubah tanpa lengan dengan kerah silang emas
  add('kain', tr(new THREE.LatheGeometry(BADAN.map(([r, y]) => new THREE.Vector2(r, y)), 32), { s: [1, 1, PIPIH] }), P.jubah, ikatBadan);
  for (const sx of [1, -1]) {
    const titik = [[.13, 1.15], [.07, 1.0], [-.02 * sx, .86], [-.08 * sx, .72]].map(([x, y]) => V(x * sx, y, depanBadan(x * sx, y, sx > 0 ? .016 : .01)));
    add('kain', new THREE.TubeGeometry(new THREE.CatmullRomCurve3(titik), 20, .022, 6), P.emas, ikatBadan);
  }
  // sabuk emas dengan simpul dan dua ujung kain
  add('kain', tr(new THREE.TorusGeometry(.256, .042, 10, 36), { r: [Math.PI / 2, 0, 0], s: [1, PIPIH, 1], p: V(0, .64, 0) }), P.emas, kaku('pinggul'));
  add('kain', ball(V(.12, .64, depanBadan(.12, .64, .03)), [.055, .05, .035]), P.emas, kaku('pinggul'));
  for (const [x, rz] of [[.1, .12], [.15, -.1]]) add('kain', tr(new THREE.BoxGeometry(.055, .2, .016), { r: [-.15, 0, rz], p: V(x, .53, depanBadan(x, .55, .03)) }), P.emas, kaku('pinggul'));
  // rok pendek dengan pinggiran emas
  add('kain', tr(new THREE.LatheGeometry([[.262, .66], [.278, .56], [.295, .46]].map(([r, y]) => new THREE.Vector2(r, y)), 32), { s: [1, 1, .86] }), P.jubahTua, kaku('pinggul'));
  add('kain', tr(new THREE.TorusGeometry(.295, .016, 6, 36), { r: [Math.PI / 2, 0, 0], s: [1, .86, 1], p: V(0, .46, 0) }), P.emas, kaku('pinggul'));
  // syal giok dan ekornya yang jatuh di punggung
  add('kain', tr(new THREE.TorusGeometry(.13, .055, 10, 24), { r: [Math.PI / 2, 0, 0], s: [1, .9, 1], p: V(0, 1.17, 0) }), P.syal, kaku('dada'));
  add('kain', tr(limb(V(-.04, 1.15, -.13), V(-.1, .84, -.25), .045, .03, 8), { }), P.syal, kaku('dada'));

  // lengan
  for (const [s, sx] of [['Ki', 1], ['Ka', -1]]) {
    const bahu = B['lenganAtas' + s], siku = B['lenganBawah' + s], tangan = B['tangan' + s], arah = tangan.clone().sub(siku).normalize();
    add('kulit', limb(bahu.clone().add(V(0, .02, 0)), siku, .068, .058), P.kulit, kaku('lenganAtas' + s));
    add('kulit', limb(siku, tangan, .056, .05), P.kulit, kaku('lenganBawah' + s));
    add('kulit', ball(tangan.clone().addScaledVector(arah, .045), [.066, .075, .062]), P.kulit, kaku('tangan' + s));
    add('kulit', ball(tangan.clone().addScaledVector(arah, .02).add(V(-sx * .01, 0, .055)), [.025, .035, .025], 10), P.kulit, kaku('tangan' + s));
    // pelindung lengan bersisik dan cincin emas di pergelangan
    add('kain', limb(siku.clone().lerp(tangan, .25), siku.clone().lerp(tangan, .95), .068, .06), P.sisik, kaku('lenganBawah' + s));
    for (const k of [.38, .62]) add('kain', tr(new THREE.TorusGeometry(.066, .009, 6, 20), { q: new THREE.Quaternion().setFromUnitVectors(FWD, arah), p: siku.clone().lerp(tangan, k) }), P.sisikTua, kaku('lenganBawah' + s));
    add('kain', tr(new THREE.TorusGeometry(.06, .015, 6, 20), { q: new THREE.Quaternion().setFromUnitVectors(FWD, arah), p: siku.clone().lerp(tangan, .93) }), P.emas, kaku('lenganBawah' + s));
    if (sx > 0) {
      // bahu kiri: tiga lempeng sisik naga bertumpuk
      [[.02, .07, .125, P.sisik], [.04, .015, .112, P.sisikTua], [.052, -.04, .1, P.sisik]].forEach(([dx, dy, r, w], i) => {
        add('kain', tr(new THREE.SphereGeometry(1, 18, 10, 0, Math.PI * 2, 0, Math.PI / 2), { s: [r, r * .72, r], r: [0, 0, -.45 - i * .1], p: bahu.clone().add(V(dx, dy, 0)) }), w, kaku('lenganAtas' + s));
      });
      add('kain', tr(new THREE.TorusGeometry(.125, .012, 6, 28), { r: [Math.PI / 2, 0, -.45], p: bahu.clone().add(V(.02, .07, 0)) }), P.emas, kaku('lenganAtas' + s));
    } else add('kain', ball(bahu.clone().add(V(0, .015, 0)), [.085, .07, .085]), P.jubah, kaku('lenganAtas' + s));
  }

  // kaki: celana, balutan, sepatu
  for (const s of ['Ki', 'Ka']) {
    const paha = B['paha' + s], lutut = B['betis' + s], x = paha.x;
    add('kain', limb(paha.clone().add(V(0, .03, 0)), lutut, .098, .082), P.celana, kaku('paha' + s));
    add('kain', limb(lutut.clone().add(V(0, .02, 0)), V(x, .08, 0), .078, .062), P.celana, kaku('betis' + s));
    for (const y of [.12, .17, .22]) add('kain', tr(new THREE.TorusGeometry(.068, .012, 6, 20), { r: [Math.PI / 2, 0, 0], p: V(x, y, 0) }), P.perban, kaku('betis' + s));
    add('kain', ball(V(x, .055, .045), [.08, .055, .135]), P.sepatu, kaku('betis' + s));
  }

  // ikat kepala hijau tua dengan lempeng emas, permata giok, tanduk mahkota naga, dan dua ujung di belakang
  const yIkat = 1.745, kIkat = Math.sqrt(1 - ((yIkat - HC.y) / HR.y) ** 2);
  add('kain', tr(new THREE.CylinderGeometry(1, 1, .07, 44, 1, true), { s: [HR.x * kIkat + .012, 1, HR.z * kIkat + .012], p: V(0, yIkat, 0) }), P.ikat, kaku('kepala'));
  add('kain', tempel(new THREE.BoxGeometry(.15, .075, .02), 0, yIkat, .02), P.emas, kaku('kepala'));
  add('cahaya', tempel(new THREE.SphereGeometry(.024, 12, 8), 0, yIkat, .034), P.permata, kaku('kepala'));
  for (const sx of [-1, 1]) {
    const pangkal = V(sx * .425, yIkat + .01, .1);
    add('kain', cone(pangkal, V(sx * .6, 1, -.35), .045, .32), P.emas, kaku('kepala'));
    add('kain', cone(pangkal.clone().add(V(0, -.01, -.09)), V(sx * .9, .55, -.5), .03, .2), P.emas, kaku('kepala'));
    add('kain', tr(new THREE.BoxGeometry(.05, .28, .012), { r: [.35, 0, sx * .12], p: V(sx * .05, yIkat - .13, -HR.z * kIkat - .04) }), P.ikat, kaku('kepala'));
  }

  // rambut: tudung di atas ikat kepala, rambut belakang, jambul besar tersibak ke belakang, dua helai jatuh, cambang
  const RC = V(0, 1.8, -.03), RR = V(.47, .46, .43);
  add('rambut', tr(new THREE.SphereGeometry(1, 40, 20, 0, Math.PI * 2, 0, Math.PI * .5), { s: [RR.x, RR.y, RR.z], p: RC }), P.rambut, kaku('kepala'));
  add('rambut', tr(new THREE.SphereGeometry(1, 36, 18, Math.PI - .4, Math.PI + .8, Math.PI * .42, Math.PI * .36), { s: [.49, .5, .45], p: V(0, 1.76, -.03) }), P.rambut, kaku('kepala'));
  const sisirBelakang = V(0, .3, -1).normalize();
  // [azimut, elevasi, jari-jari, panjang, condong ke belakang]
  for (const [az, el, r, h, k] of [
    [0, 35, .14, .44, .55], [28, 40, .12, .4, .6], [-28, 40, .12, .4, .6], [0, 62, .14, .5, .7],
    [55, 30, .12, .42, .65], [-55, 30, .12, .42, .65], [90, 22, .11, .42, .75], [-90, 22, .11, .42, .75],
    [125, 25, .11, .44, .8], [-125, 25, .11, .44, .8], [160, 35, .12, .48, .85], [-160, 35, .12, .48, .85],
    [180, 55, .13, .5, .85], [150, 62, .12, .46, .8], [-150, 62, .12, .46, .8], [100, 52, .11, .4, .75], [-100, 52, .11, .4, .75], [180, 15, .1, .4, .9]]) {
    const a = THREE.MathUtils.degToRad(az), e = THREE.MathUtils.degToRad(el);
    const keluar = V(Math.sin(a) * Math.cos(e), Math.sin(e), Math.cos(a) * Math.cos(e));
    const p = V(RC.x + keluar.x * RR.x * .8, RC.y + keluar.y * RR.y * .8, RC.z + keluar.z * RR.z * .8);
    add('rambut', cone(p, keluar.clone().multiplyScalar(1 - k).addScaledVector(sisirBelakang, k).add(V(0, .25, 0)), r, h, 7), P.rambut, kaku('kepala'));
  }
  for (const [x, dx, h] of [[-.12, -.25, .24], [.1, .15, .18]]) add('rambut', cone(V(x, 1.86, .36), V(dx, -1, .45), .045, h, 6), P.rambut, kaku('kepala'));
  for (const sx of [-1, 1]) add('rambut', cone(V(sx * .42, 1.82, .1), V(sx * .1, -1, .2), .07, .28, 7), P.rambut, kaku('kepala'));

  // wajah: mata naga (pupil celah), kelopak, alis tegas, mulut
  const yMata = 1.575;
  for (const sx of [-1, 1]) {
    const x = sx * .155;
    add('cahaya', tempel(new THREE.SphereGeometry(1, 20, 12).scale(.078, .098, .012), x, yMata, .004), P.putih, kaku('kepala'));
    add('cahaya', tempel(new THREE.SphereGeometry(1, 20, 12).scale(.06, .08, .012), x, yMata - .008, .009), P.iris, kaku('kepala'));
    add('cahaya', tempel(new THREE.SphereGeometry(1, 14, 10).scale(.016, .056, .012), x, yMata - .008, .014), P.pupil, kaku('kepala'));
    add('cahaya', tempel(new THREE.SphereGeometry(1, 10, 8).scale(.02, .024, .012), x - .022, yMata + .03, .019), P.putih, kaku('kepala'));
    add('cahaya', tempel(new THREE.SphereGeometry(1, 8, 6).scale(.01, .01, .012), x + .022, yMata - .038, .019), P.putih, kaku('kepala'));
    add('cahaya', tempel(new THREE.BoxGeometry(.175, .024, .012), x + sx * .006, yMata + .094, .014, -sx * .14), P.garis, kaku('kepala'));
    add('cahaya', tempel(new THREE.BoxGeometry(.05, .02, .012), x + sx * .09, yMata + .07, .014, -sx * .6), P.garis, kaku('kepala'));
    add('cahaya', tempel(new THREE.BoxGeometry(.125, .026, .012), sx * .15, 1.69, .012, sx * .26), P.rambut, kaku('kepala'));
  }
  add('cahaya', tempel(new THREE.BoxGeometry(.09, .016, .01), .01, 1.425, .008, .12), P.mulut, kaku('kepala'));
  add('cahaya', tempel(new THREE.BoxGeometry(.028, .014, .01), .058, 1.434, .008, .75), P.mulut, kaku('kepala'));

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
  ];
  const meshes = MATS.map((m, mi) => {
    const g = mesh[m.name], a = g.attributes, idx = g.index.array;
    const big = a.position.count > 65535;
    return { primitives: [{ mode: 4, material: mi,
      indices: acc(big ? new Uint32Array(idx) : new Uint16Array(idx), 'SCALAR', big ? 5125 : 5123, 34963),
      attributes: {
        POSITION: acc(new Float32Array(a.position.array), 'VEC3', 5126, 34962, true),
        NORMAL: acc(new Float32Array(a.normal.array), 'VEC3', 5126, 34962),
        COLOR_0: acc(new Float32Array(a.color.array), 'VEC3', 5126, 34962),
        JOINTS_0: acc(new Uint16Array(a.skinIndex.array), 'VEC4', 5123, 34962),
        WEIGHTS_0: acc(new Float32Array(a.skinWeight.array), 'VEC4', 5126, 34962),
      } }] };
  });
  const ibm = new Float32Array(skinJoints.length * 16);
  skinJoints.forEach((ni, k) => ibm.set(objs[ni].matrixWorld.clone().invert().elements, k * 16));
  const ibmAcc = acc(ibm, 'MAT4', 5126);
  // klip animasi disalin apa adanya; target node 0–14 tetap sama
  const salin = ai => { const a = src.accessors[ai], bv = src.bufferViews[a.bufferView], off = (bv.byteOffset || 0) + (a.byteOffset || 0); return new Float32Array(srcBuf.buffer.slice(srcBuf.byteOffset + off, srcBuf.byteOffset + off + a.count * N[a.type] * 4)); };
  const animations = src.animations.map(an => ({ name: an.name, channels: an.channels, samplers: an.samplers.map(s => ({ interpolation: s.interpolation, input: acc(salin(s.input), 'SCALAR', 5126, undefined, true), output: acc(salin(s.output), src.accessors[s.output].type, 5126) })) }));

  const info = { id: 'azam', nama: 'Azam', julukan: 'Pawang Naga', asal: 'Rawa Hijau', senjata: 'Naga hijau panggilan', elemen: 'Naga', varian, warna: P, skala: .72, tinggiMeter: 1.78, klip: src.animations.map(a => a.name) };
  const nodes = RIG.map(n => Object.fromEntries(Object.entries(n).filter(([k]) => ['name', 'translation', 'rotation', 'children'].includes(k))));
  const nm = ['body', 'kulit', 'rambut', 'glow'];
  meshes.forEach((m, i) => nodes.push({ name: 'azam_' + nm[i], mesh: i, skin: 0 }));
  nodes.push({ name: 'azam', scale: [.72, .72, .72], extras: info, children: [14, 15, 16, 17, 18] });
  nodes.push({ name: 'petarung_azam', extras: info, children: [19] });
  const bin = Buffer.concat(chunks);
  const gltf = { asset: { version: '2.0', generator: 'Badai Shinobi tools/buat-azam.mjs' }, scene: 0, scenes: [{ name: 'AuxScene', nodes: [20] }], nodes, meshes, materials: MATS, skins: [{ inverseBindMatrices: ibmAcc, joints: skinJoints, skeleton: 14 }], animations, accessors, bufferViews, buffers: [{ byteLength: bin.length, uri: 'data:application/octet-stream;base64,' + bin.toString('base64') }] };
  const out = join(ROOT, 'assets/petarung', varian === 'p1' ? 'azam.gltf.json' : 'azam-p2.gltf.json');
  writeFileSync(out, JSON.stringify(gltf));
  console.log(out, (bin.length / 1024).toFixed(0) + ' KB', Object.fromEntries(MATS.map(m => [m.name, mesh[m.name].attributes.position.count])));
}
tulis('p1'); tulis('p2');
