// penonton.js — penonton bergerak di sekeliling arena Badai Shinobi (Three.js r155 ke atas).
//
// npc-penonton.glb berisi 19 karakter orisinal (NPC_<id>) dengan satu rangka bersama dan klip animasi:
//   diam, sorak, tepuk, lambai, tunjuk, lompat, ngobrol, jaga, tabuh, bungkuk, tongkat, jalan, rusa_diam, rusa_merumput
// Setiap karakter menyimpan extras: { id, nama, peran, klip, skala }.
// Penonton hanya ditempatkan di arena.titikPenonton (NPC_SPOTS di file arena), yang semuanya di luar area tarung P1/P2.
//
// Pemakaian:
//   const paket = await muatPaketPenonton('assets/npc-penonton.glb');
//   const penonton = pasangPenonton(scene, arena, paket, { jumlah: 40 });
//   loop: penonton.update(dt);
//   saat pukulan keras / KO: penonton.reaksi('sorak', 2.5);

import * as THREE from '../lib/three/three.module.js';
import { GLTFLoader } from '../lib/three/addons/loaders/GLTFLoader.js';
import * as SkeletonUtils from '../lib/three/addons/utils/SkeletonUtils.js';

const loader = new GLTFLoader();

/** Muat paket karakter + klip (url .glb atau isi GLB berupa ArrayBuffer). Nama tulang tiap karakter disamakan supaya semua klip bisa dipakai bersama. */
export async function muatPaketPenonton(url){
  const gltf = await (typeof url === 'string' ? loader.loadAsync(url) : loader.parseAsync(url, ''));
  const karakter = {};
  for(const g of gltf.scene.children){
    if(!g.userData?.npc) continue;
    g.traverse(o => { if(o.isBone) o.name = o.name.replace(/_\d+$/, ''); });
    g.position.set(0, 0, 0);
    karakter[g.userData.id] = g;
  }
  const klip = Object.fromEntries(gltf.animations.map(c => [c.name, c]));
  return { karakter, klip };
}

const BOBOT = { tetua:1, pemburu:3, nyonya:3, saudagar:3, penjaga:2, penjaga2:2, biksu:2, peramu:2, pandai:2, petani:3, ibu:3, kakek:2, anakLaki:3, anakPerempuan:3, penabuh:1, pengembara:2, petarung:2, pendekar:2, rusa:1 };
const BATAS = { tetua:1, penabuh:2, rusa:2, penjaga:3, penjaga2:3, biksu:3, kakek:2 };
const REAKSI = { anak:'lompat', biksu:'tepuk', tua:'tepuk', tetua:'tepuk', pemusik:'tabuh' };

function gradienToon(){
  const t = new THREE.DataTexture(new Uint8Array([70, 135, 205, 255]), 4, 1, THREE.RedFormat);
  t.minFilter = t.magFilter = THREE.NearestFilter; t.generateMipmaps = false; t.needsUpdate = true; return t;
}
function tintaMaterial(warna, tebal){
  const m = new THREE.MeshBasicMaterial({ color:warna, side:THREE.BackSide });
  m.onBeforeCompile = sh => { sh.vertexShader = sh.vertexShader.replace('#include <begin_vertex>', `#include <begin_vertex>\ntransformed += normalize(normal) * ${tebal.toFixed(4)};`); };
  m.customProgramCacheKey = () => 'tinta-npc-' + tebal;
  return m;
}

/**
 * Tempatkan penonton di titik-titik arena dan buat mereka bergerak.
 * @param {THREE.Scene} scene
 * @param {object} arena   hasil muatArena() (butuh arena.titikPenonton)
 * @param {object} paket   hasil muatPaketPenonton()
 * @param {{jumlah?:number, jarakMin?:number, toon?:boolean, garisTinta?:boolean, warnaGaris?:string, bayangan?:boolean, mondarMandir?:number}} [opsi]
 */
export function pasangPenonton(scene, arena, paket, opsi = {}){
  const { jumlah = 40, jarakMin = 1.15, toon = true, garisTinta = true, warnaGaris = '#1c1824', bayangan = true, mondarMandir = .12 } = opsi;
  const grup = new THREE.Group(); grup.name = 'PENONTON'; scene.add(grup);
  const gradien = toon ? gradienToon() : null, tinta = garisTinta ? tintaMaterial(warnaGaris, .016) : null;
  const sampah = [gradien, tinta].filter(Boolean);

  // siapkan geometri toon (normal datar) + geometri garis (normal halus) satu kali per karakter
  const siap = {};
  for(const [id, g] of Object.entries(paket.karakter)){
    const mesh = g.getObjectByProperty('isSkinnedMesh', true); if(!mesh) continue;
    const asli = mesh.geometry;
    const datar = asli.index ? asli.toNonIndexed() : asli.clone(); datar.computeVertexNormals();
    const halus = asli.clone(); halus.computeVertexNormals();
    const mat = toon ? new THREE.MeshToonMaterial({ vertexColors:true, gradientMap:gradien }) : mesh.material;
    siap[id] = { template:g, datar, halus, mat, meta:g.userData };
    sampah.push(datar, halus); if(toon) sampah.push(mat);
  }

  // pilih titik: acak, saling berjarak, tidak lebih dari `jumlah`
  const titik = [...(arena.titikPenonton ?? [])].sort(() => Math.random() - .5), dipakai = [];
  for(const t of titik){ if(dipakai.length >= jumlah) break; if(dipakai.every(d => d.posisi.distanceTo(t.posisi) >= jarakMin)) dipakai.push(t); }

  const hitung = {};
  function pilihKarakter(t){
    const kandidat = Object.keys(siap).filter(id => {
      if((hitung[id] ?? 0) >= (BATAS[id] ?? 99)) return false;
      if(id === 'rusa' && (t.jenis !== 'tanah' || t.baris < 1)) return false;
      return true;
    });
    let total = kandidat.reduce((a, id) => a + (BOBOT[id] ?? 1), 0), r = Math.random() * total;
    for(const id of kandidat){ r -= BOBOT[id] ?? 1; if(r <= 0) return id; }
    return kandidat[0];
  }

  // jalur mondar-mandir tidak boleh memotong collider (bangunan, pohon, pagar)
  function jalurAman(a, b){
    for(let k = 1; k < 6; k++){
      const x = a.x + (b.x - a.x) * k / 6, z = a.z + (b.z - a.z) * k / 6;
      for(const c of arena.colliders ?? []){
        if(c.nama.includes('batas')) continue;
        const dx = x - c.pusat.x, dz = z - c.pusat.z, cs = Math.cos(c.sudutY), sn = Math.sin(c.sudutY);
        if(Math.abs(dx * cs - dz * sn) < c.ukuran.x / 2 + .4 && Math.abs(dx * sn + dz * cs) < c.ukuran.z / 2 + .4) return false;
      }
    }
    return true;
  }
  const npc = [];
  for(const t of dipakai){
    const id = pilihKarakter(t); if(!id) continue; hitung[id] = (hitung[id] ?? 0) + 1;
    const s = siap[id], obj = SkeletonUtils.clone(s.template);
    obj.position.copy(t.posisi); obj.rotation.y = t.arahY + (Math.random() - .5) * .5;
    obj.scale.multiplyScalar(.94 + Math.random() * .12);
    const mesh = obj.getObjectByProperty('isSkinnedMesh', true);
    mesh.geometry = s.datar; mesh.material = s.mat; mesh.castShadow = bayangan; mesh.receiveShadow = bayangan; mesh.frustumCulled = false;
    if(tinta){ const garis = new THREE.SkinnedMesh(s.halus, tinta); garis.bind(mesh.skeleton, mesh.bindMatrix); garis.frustumCulled = false; mesh.parent.add(garis); }
    grup.add(obj);
    const mixer = new THREE.AnimationMixer(obj), aksi = {};
    for(const nama of [...new Set([...s.meta.klip, 'sorak', 'tepuk', 'lompat', 'tunjuk', 'jalan'])]){
      if(!paket.klip[nama] || (s.meta.peran === 'hewan') !== nama.startsWith('rusa_')) continue;
      aksi[nama] = mixer.clipAction(paket.klip[nama]);
    }
    const n = { obj, mixer, aksi, meta:s.meta, sekarang:null, timer:0, reaksi:0, asal:t.posisi.clone(), arahAsal:obj.rotation.y, jalan:null };
    main(n, s.meta.klip[Math.floor(Math.random() * s.meta.klip.length)], 0);
    n.sekarang.time = Math.random() * n.sekarang.getClip().duration;
    n.timer = 3 + Math.random() * 7;
    // sebagian penonton di tanah mondar-mandir ke titik tetangga di baris yang sama
    if(t.jenis === 'tanah' && s.meta.peran !== 'hewan' && s.meta.peran !== 'pemusik' && Math.random() < mondarMandir){
      const tetangga = titik.find(o => o !== t && !dipakai.includes(o) && o.jenis === 'tanah' && o.baris === t.baris && o.posisi.distanceTo(t.posisi) > 1.8 && o.posisi.distanceTo(t.posisi) < 4 && jalurAman(t.posisi, o.posisi));
      if(tetangga) n.jalan = { a:t.posisi.clone(), b:tetangga.posisi.clone(), keB:true, jeda:2 + Math.random() * 3 };
    }
    npc.push(n);
  }

  function main(n, nama, pudar = .35){
    const a = n.aksi[nama]; if(!a || a === n.sekarang) return;
    a.reset(); a.setEffectiveTimeScale(.9 + Math.random() * .25); a.setEffectiveWeight(1); a.play();
    if(n.sekarang && pudar > 0) n.sekarang.crossFadeTo(a, pudar, false); else if(n.sekarang) n.sekarang.stop();
    n.sekarang = a;
  }
  const _arah = new THREE.Vector3();

  return {
    grup, npc,
    /** Panggil setiap frame. */
    update(dt){
      for(const n of npc){
        n.mixer.update(dt);
        if(n.reaksi > 0){ n.reaksi -= dt; if(n.reaksi <= 0){ main(n, n.meta.klip[0]); n.timer = 2 + Math.random() * 4; } continue; }
        if(n.jalan){
          const j = n.jalan;
          if(j.jeda > 0){
            j.jeda -= dt;
            if(j.jeda <= 0){ main(n, 'jalan', .3); }
            else { n.timer -= dt; if(n.timer <= 0){ main(n, n.meta.klip[Math.floor(Math.random() * n.meta.klip.length)]); n.timer = 3 + Math.random() * 4; } }
            continue;
          }
          const tujuan = j.keB ? j.b : j.a;
          _arah.subVectors(tujuan, n.obj.position); _arah.y = 0;
          const d = _arah.length();
          if(d < .05){ j.keB = !j.keB; j.jeda = 3 + Math.random() * 5; main(n, n.meta.klip[0]); n.obj.rotation.y = n.arahAsal; continue; }
          const v = Math.min(d, 1.05 * dt * (n.meta.skala ?? 1));
          n.obj.position.addScaledVector(_arah.normalize(), v);
          n.obj.rotation.y = Math.atan2(_arah.x, _arah.z);
          continue;
        }
        n.timer -= dt;
        if(n.timer <= 0){ const k = n.meta.klip; main(n, k[Math.floor(Math.random() * k.length)]); n.timer = 4 + Math.random() * 6; }
      }
    },
    /** Semua penonton bereaksi bersamaan, misalnya saat pukulan keras atau KO. jenis: 'sorak' | 'tepuk' | 'tunjuk' */
    reaksi(jenis = 'sorak', durasi = 2.5){
      for(const n of npc){
        if(n.meta.peran === 'hewan') continue;
        const k = REAKSI[n.meta.peran] && jenis === 'sorak' ? REAKSI[n.meta.peran] : jenis;
        setTimeout(() => {
          if(n.jalan){ n.jalan.jeda = durasi + 1; n.obj.rotation.y = n.arahAsal; }
          main(n, n.aksi[k] ? k : 'sorak', .2); n.reaksi = durasi * (.85 + Math.random() * .3);
        }, Math.random() * 280);
      }
    },
    /** Lepas semua penonton dan bebaskan memori GPU. */
    lepas(){
      scene.remove(grup);
      for(const n of npc) n.mixer.stopAllAction();
      for(const x of sampah) x.dispose?.();
    }
  };
}
