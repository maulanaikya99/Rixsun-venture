// petarung.js — pemuat petarung .glb untuk game Badai Shinobi (three.js r160).
// Diadaptasi dari muat-petarung.js (paket aset): material "figur" (halus seperti vinil) atau "toon",
// garis tinta, bayangan, dan klip animasi bawaan. Bedanya, di sini satu file dimuat sekali sebagai
// cetakan lalu digandakan untuk setiap petarung dan partner, dan setiap gandaan punya material
// sendiri supaya kilatan saat terkena pukulan hanya muncul pada petarung yang dipukul.
//
// Rangka (15 tulang, sama untuk semua petarung): akar, pinggul, perut, dada, kepala,
// lenganAtasKi/Ka, lenganBawahKi/Ka, tanganKi/Ka, pahaKi/Ka, betisKi/Ka. Ki = kiri karakter (+X).
// Klip bawaan: siaga, kuda_kuda, jalan, pukul.

import * as THREE from '../lib/three/three.module.js';
import { GLTFLoader } from '../lib/three/addons/loaders/GLTFLoader.js';
import { RoomEnvironment } from '../lib/three/addons/environments/RoomEnvironment.js';
import { mergeGeometries, mergeVertices } from '../lib/three/addons/utils/BufferGeometryUtils.js';
import { clone as klonRangka } from '../lib/three/addons/utils/SkeletonUtils.js';

const loader = new GLTFLoader();
// Tekstur wajah dibaca lewat elemen gambar, bukan fetch: halaman artifact menolak fetch ke alamat blob:,
// sedangkan gambar dari blob: tetap diizinkan. Hasilnya sama di semua browser.
loader.register(parser => {
  const tl = new THREE.TextureLoader(parser.options.manager);
  tl.setCrossOrigin(parser.options.crossOrigin);
  parser.textureLoader = tl;
  return { name: 'badai_shinobi_gambar_tanpa_fetch' };
});
export const TULANG = ['akar', 'pinggul', 'perut', 'dada', 'kepala', 'lenganAtasKi', 'lenganBawahKi', 'tanganKi', 'lenganAtasKa', 'lenganBawahKa', 'tanganKa', 'pahaKi', 'betisKi', 'pahaKa', 'betisKa'];

let envCache = null;
function lingkunganStudio(renderer){
  if(!renderer) return null;
  if(envCache && envCache.renderer === renderer) return envCache.tex;
  const pm = new THREE.PMREMGenerator(renderer);
  const tex = pm.fromScene(new RoomEnvironment(renderer), .04).texture; pm.dispose();
  envCache = { renderer, tex }; return tex;
}

const NOISE = `
  float h31(vec3 p){ p = fract(p * .1031); p += dot(p, p.yzx + 33.33); return fract((p.x + p.y) * p.z); }
  float vn(vec3 p){ vec3 i = floor(p), f = fract(p); f = f * f * (3. - 2. * f);
    return mix(mix(mix(h31(i), h31(i + vec3(1,0,0)), f.x), mix(h31(i + vec3(0,1,0)), h31(i + vec3(1,1,0)), f.x), f.y),
               mix(mix(h31(i + vec3(0,0,1)), h31(i + vec3(1,0,1)), f.x), mix(h31(i + vec3(0,1,1)), h31(i + vec3(1,1,1)), f.x), f.y), f.z); }`;
function denganPosisiObjek(m, frag){
  m.onBeforeCompile = sh => {
    sh.vertexShader = sh.vertexShader.replace('#include <common>', '#include <common>\nvarying vec3 vOP;').replace('#include <begin_vertex>', '#include <begin_vertex>\nvOP = position;');
    sh.fragmentShader = sh.fragmentShader.replace('#include <common>', '#include <common>\nvarying vec3 vOP;' + NOISE).replace('#include <color_fragment>', '#include <color_fragment>\n' + frag);
  };
  m.customProgramCacheKey = () => 'bs-' + frag.length;
  return m;
}
const gradien = arr => { const t = new THREE.DataTexture(new Uint8Array(arr.flatMap(v => [v, v, v, 255])), arr.length, 1); t.minFilter = t.magFilter = THREE.NearestFilter; t.generateMipmaps = false; t.needsUpdate = true; return t; };
let gradToon = null;

/** satu set material baru (dibuat per petarung; program shader tetap dipakai bersama) */
function bahan(gaya, env){
  let b;
  if(gaya === 'toon'){
    gradToon = gradToon || [gradien([118, 205, 255]), gradien([214, 242, 255])];
    const [g3, g2] = gradToon;
    b = { kain:new THREE.MeshToonMaterial({ vertexColors:true, gradientMap:g3, side:THREE.DoubleSide }), kulit:new THREE.MeshToonMaterial({ vertexColors:true, gradientMap:g2 }) };
    b.rambut = b.kain;
    b.wajah = map => new THREE.MeshToonMaterial({ map, gradientMap:g2, transparent:true, depthWrite:false, polygonOffset:true, polygonOffsetFactor:-4, polygonOffsetUnits:-4, emissive:0xffffff, emissiveMap:map, emissiveIntensity:.18 });
  } else {
    const e = env ? { envMap:env } : {};
    b = {
      kain:denganPosisiObjek(new THREE.MeshPhysicalMaterial({ vertexColors:true, roughness:.86, metalness:0, sheen:.6, sheenRoughness:.55, sheenColor:new THREE.Color(.55, .55, .55), envMapIntensity:.55, side:THREE.DoubleSide, ...e }), `
        { vec3 q = vOP * 190.; float weave = .5 + .25 * (sin(q.x + sin(q.y * .5)) * sin(q.y) + sin(q.z) * sin(q.y + 1.3));
          float mott = vn(vOP * 26.) * .6 + vn(vOP * 75.) * .4;
          diffuseColor.rgb *= .9 + .1 * weave + .13 * (mott - .5); }`),
      kulit:denganPosisiObjek(new THREE.MeshPhysicalMaterial({ vertexColors:true, roughness:.5, metalness:0, specularIntensity:.35, sheen:.35, sheenRoughness:.5, sheenColor:new THREE.Color(1, .72, .62), envMapIntensity:.45, ...e }), `
        diffuseColor.rgb *= .985 + .03 * (vn(vOP * 60.) - .5);`),
      rambut:new THREE.MeshPhysicalMaterial({ vertexColors:true, roughness:.44, metalness:0, clearcoat:.18, clearcoatRoughness:.4, envMapIntensity:.6, side:THREE.DoubleSide, ...e }),
    };
    b.rambut.onBeforeCompile = sh => {
      sh.vertexShader = sh.vertexShader.replace('#include <common>', '#include <common>\nattribute vec2 huv;\nvarying vec2 vH;').replace('#include <begin_vertex>', '#include <begin_vertex>\nvH = huv;');
      sh.fragmentShader = sh.fragmentShader.replace('#include <common>', '#include <common>\nvarying vec2 vH;').replace('#include <color_fragment>', `#include <color_fragment>
        { float g = sin(vH.y * 6.2832 * 7. + vH.x * 2.) * .5 + .5, g2 = sin(vH.y * 6.2832 * 17. - vH.x * 5.) * .5 + .5;
          diffuseColor.rgb *= mix(1., .9 + .07 * g + .05 * g2, step(.001, vH.x + vH.y)); }`);
    };
    b.rambut.customProgramCacheKey = () => 'bs-rambut';
    b.wajah = map => new THREE.MeshPhysicalMaterial({ map, transparent:true, depthWrite:false, polygonOffset:true, polygonOffsetFactor:-4, polygonOffsetUnits:-4, roughness:.45, specularIntensity:.35, sheen:.35, sheenRoughness:.5, sheenColor:new THREE.Color(1, .72, .62), envMapIntensity:.45, ...e });
  }
  b.cahaya = new THREE.MeshBasicMaterial({ vertexColors:true, toneMapped:false });
  return b;
}
function bahanGaris(warna, tebal){
  const m = new THREE.MeshBasicMaterial({ color:warna, side:THREE.BackSide });
  m.onBeforeCompile = sh => { sh.vertexShader = sh.vertexShader.replace('#include <begin_vertex>', `#include <begin_vertex>\ntransformed += normalize(normal) * ${tebal.toFixed(5)};`); };
  m.customProgramCacheKey = () => 'bs-garis-' + tebal;
  return m;
}

/** Unduh file petarung (.glb), atau urai isi GLB yang sudah ada di memori (ArrayBuffer). */
export function unduhPetarung(sumber){ return typeof sumber === 'string' ? loader.loadAsync(sumber) : loader.parseAsync(sumber, ''); }

/**
 * Siapkan cetakan dari hasil unduhPetarung(): data karakter, ukuran rangka saat diam, dan geometri garis tinta.
 * Dipanggil sekali per file.
 */
export function siapkanCetakan(gltf){
  const objek = gltf.scene; objek.updateMatrixWorld(true);
  const kontainer = objek.children.find(o => o.userData && o.userData.id) || objek;
  const info = { ...kontainer.userData };
  const kulitSkin = [];
  objek.traverse(o => {
    if(!o.isMesh) return;
    const nama = (o.material && o.material.name) || '';
    if(o.geometry.attributes._huv){ o.geometry.setAttribute('huv', o.geometry.attributes._huv); o.geometry.deleteAttribute('_huv'); }
    if(nama.startsWith('wajah') && o.material.map) o.material.map.colorSpace = THREE.SRGBColorSpace;
    if(o.isSkinnedMesh && ['kain', 'kulit', 'rambut'].includes(nama)) kulitSkin.push(o);
  });
  // garis tinta: kulit luar yang dilas dari kain + kulit + rambut
  let geoGaris = null;
  if(kulitSkin.length){
    const src = kulitSkin.map(m => { const g = new THREE.BufferGeometry(); for(const k of ['position', 'skinIndex', 'skinWeight']) g.setAttribute(k, m.geometry.attributes[k]); g.setIndex(m.geometry.index); return g; });
    geoGaris = mergeVertices(mergeGeometries(src), 1e-4); geoGaris.computeVertexNormals();
  }
  // posisi & rotasi tulang saat diam, dalam ruang model (meter)
  const tulang = {}, akar = objek.getObjectByName('akar');
  const pusat = objek.getWorldPosition(new THREE.Vector3()), qPusat = objek.getWorldQuaternion(new THREE.Quaternion()).invert();
  for(const n of TULANG){
    const b = objek.getObjectByName(n); if(!b) continue;
    tulang[n] = { posisi:b.getWorldPosition(new THREE.Vector3()).sub(pusat), qDunia:qPusat.clone().multiply(b.getWorldQuaternion(new THREE.Quaternion())), qLokal:b.quaternion.clone(), pLokal:b.position.clone() };
  }
  return { gltf, objek, info, geoGaris, tulang, adaAkar:!!akar };
}

/**
 * Buat satu petarung dari cetakan.
 * opsi: renderer (pantulan studio gaya figur), gaya 'figur' | 'toon', garisTinta, warnaGaris, tebalGaris, bayangan
 */
export function buatPetarung(cetakan, opsi = {}){
  const gaya = opsi.gaya ?? 'figur', env = gaya === 'figur' ? lingkunganStudio(opsi.renderer) : null, B = bahan(gaya, env);
  const objek = klonRangka(cetakan.objek);
  const bahanDipakai = new Set(), kulitSkin = [];
  objek.traverse(o => {
    if(!o.isMesh) return;
    const nama = (o.material && o.material.name) || '';
    if(nama.startsWith('wajah')){ o.material = B.wajah(o.material.map); o.renderOrder = 2; }
    else if(nama === 'cahaya') o.material = B.cahaya;
    else if(B[nama]) o.material = B[nama];
    bahanDipakai.add(o.material);
    o.frustumCulled = false;
    o.castShadow = opsi.bayangan !== false && !nama.startsWith('wajah');
    o.receiveShadow = opsi.bayangan !== false;
    if(o.isSkinnedMesh && ['kain', 'kulit', 'rambut'].includes(nama)) kulitSkin.push(o);
  });
  let garis = null;
  if(opsi.garisTinta !== false && cetakan.geoGaris && kulitSkin.length){
    const tebal = opsi.tebalGaris ?? (gaya === 'toon' ? .0065 : .0042);
    garis = new THREE.SkinnedMesh(cetakan.geoGaris, bahanGaris(opsi.warnaGaris ?? '#3b2832', tebal));
    garis.frustumCulled = false; garis.castShadow = false;
    kulitSkin[0].parent.add(garis); garis.bind(kulitSkin[0].skeleton, kulitSkin[0].bindMatrix);
    bahanDipakai.add(garis.material);
  }
  const tulang = {}; for(const n of TULANG){ const b = objek.getObjectByName(n); if(b) tulang[n] = b; }
  const mixer = new THREE.AnimationMixer(objek), aksi = {};
  for(const k of cetakan.gltf.animations) aksi[k.name] = mixer.clipAction(k);
  const bahanKilat = [...bahanDipakai].filter(m => m.emissive && m !== (garis && garis.material));
  for(const m of bahanDipakai) if(m.envMapIntensity !== undefined) m.userData.envDasar = m.envMapIntensity;
  return {
    objek, tulang, mixer, aksi, garis, info:cetakan.info, cetakan,
    /** material yang bisa berkilat putih saat terkena pukulan */
    bahanKilat,
    /** atur kuat pantulan cahaya studio (1 = seperti di galeri); diturunkan di arena yang gelap */
    aturPantulan(k){ for(const m of bahanDipakai) if(m.userData.envDasar !== undefined) m.envMapIntensity = m.userData.envDasar * k; },
    lepas(){
      mixer.stopAllAction(); objek.removeFromParent();
      for(const m of bahanDipakai) m.dispose();
    }
  };
}
