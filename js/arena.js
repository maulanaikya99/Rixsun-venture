// arena.js — pemuat arena .glb untuk game Badai Shinobi (three.js r160).
// Diadaptasi dari muat-arena.js v2 (paket arena): shader langit, angin, partikel, petir, dan
// efek sinematik tetap sama. Bedanya, di sini arena dibangun SEKALI lalu bisa dipasang/dilepas
// dari scene tanpa dibangun ulang, dan cahaya utama (hemisfer, matahari, lampu titik) dipegang
// oleh game supaya jumlah lampu tetap dan shader tidak dikompilasi ulang setiap ganti arena.
//
// Isi setiap file arena-*.glb:
//   GROUND      tanah berwarna (vertex color) + permukaan lantai
//   VISUAL      bangunan, pohon, properti (satu mesh per material). Material "sinar" = berkas cahaya
//   CLOUDS      awan kumulus 3D di kejauhan
//   COLLIDERS   node kosong COL_*: posisi = pusat kotak, skala = ukuran kotak, rotasi Y = arah
//   LIGHTS      node kosong LIGHT_*: lampu titik (extras: color, intensity, distance)
//   NPC_SPOTS   node kosong NPC_SPOT_*: titik berdiri penonton di luar area tarung
//   SPAWNS      SPAWN_P1, SPAWN_P2
//   ARENA_INFO  extras: judul, suasana, radius tarung, env (langit, kabut, cahaya, warna, angin, partikel, petir)

import * as THREE from '../lib/three/three.module.js';
import { GLTFLoader } from '../lib/three/addons/loaders/GLTFLoader.js';
import { EffectComposer } from '../lib/three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from '../lib/three/addons/postprocessing/RenderPass.js';
import { ShaderPass } from '../lib/three/addons/postprocessing/ShaderPass.js';
import { UnrealBloomPass } from '../lib/three/addons/postprocessing/UnrealBloomPass.js';

const loader = new GLTFLoader();
const PI = Math.PI;

// seberapa kuat tiap material bergoyang ditiup angin (0 = diam)
const GOYANG = { daun1:.014, daun2:.014, daun3:.014, daun4:.012, daunGelap:.012, daunTerang:.016, daunMerah:.014, daunOranye:.016, daunPinus:.008, bambu:.022, bambuTua:.022, rumputGelap:.3, pakis:.12, noren1:.004, noren2:.004, noren3:.004, panji:.006 };

function gradienToon(){
  const t = new THREE.DataTexture(new Uint8Array([62, 128, 198, 255]), 4, 1, THREE.RedFormat);
  t.minFilter = t.magFilter = THREE.NearestFilter; t.generateMipmaps = false; t.needsUpdate = true;
  return t;
}
function tambalAngin(mat, amp, garis, U){
  mat.onBeforeCompile = sh => {
    Object.assign(sh.uniforms, { uTime:U.time, uWind:U.wind, uAmp:{ value:amp }, uOutline:U.outline });
    sh.vertexShader = 'uniform float uTime;\nuniform vec2 uWind;\nuniform float uAmp;\nuniform float uOutline;\n' + sh.vertexShader.replace('#include <begin_vertex>', [
      '#include <begin_vertex>',
      garis ? 'transformed += normalize(normal) * uOutline;' : '',
      'if(uAmp > 0.0){ float hg = min(max(transformed.y, 0.0), uAmp > 0.1 ? 1.0 : 16.0); float ph = dot(transformed.xz, vec2(0.21, 0.17));',
      '  float sw = sin(uTime * 1.6 + ph) * 0.7 + sin(uTime * 2.9 + ph * 2.3) * 0.3; transformed.xz += uWind * (sw * 0.6 + 0.4) * uAmp * hg; }'
    ].join('\n'));
  };
  mat.customProgramCacheKey = () => (garis ? 'ol' : 'tn') + (amp > 0 ? 's' : 'n');
  return mat;
}
function bahanSinar(warna, U){
  return new THREE.ShaderMaterial({
    uniforms:{ uCol:{ value:new THREE.Color(warna) }, uOp:{ value:.27 }, uTime:U.time },
    vertexShader:'varying vec3 vN;varying vec3 vV;varying float vY;void main(){vec4 wp=modelMatrix*vec4(position,1.0);vY=wp.y;vN=normalize(normalMatrix*normal);vec4 mv=viewMatrix*wp;vV=normalize(-mv.xyz);gl_Position=projectionMatrix*mv;}',
    fragmentShader:'uniform vec3 uCol;uniform float uOp;uniform float uTime;varying vec3 vN;varying vec3 vV;varying float vY;void main(){float f=abs(dot(normalize(vN),normalize(vV)));float a=pow(f,1.5)*uOp*smoothstep(-0.5,5.0,vY)*(1.0-smoothstep(25.0,90.0,vY));a*=0.8+0.2*sin(uTime*0.6+vY*0.25);gl_FragColor=vec4(uCol*a,a);\n#include <colorspace_fragment>\n}',
    transparent:true, depthWrite:false, blending:THREE.AdditiveBlending, side:THREE.DoubleSide, fog:false
  });
}

/* ---------- langit: gradien, matahari atau bulan, bintang, awan bergerak ---------- */
function buatLangit(sky){
  const u = {
    uZenith:{ value:new THREE.Color(sky.zenith) }, uHorizon:{ value:new THREE.Color(sky.horizon) }, uBand:{ value:new THREE.Color(sky.band) },
    uSunCol:{ value:new THREE.Color(sky.sunColor) }, uCloudL:{ value:new THREE.Color(sky.cloudLight) }, uCloudS:{ value:new THREE.Color(sky.cloudShadow) },
    uSunDir:{ value:new THREE.Vector3(...sky.sunDir).normalize() }, uSunSize:{ value:sky.sunSize }, uGlow:{ value:sky.glow }, uCover:{ value:sky.cloudCover },
    uCScale:{ value:sky.cloudScale }, uTime:{ value:0 }, uSpeed:{ value:sky.cloudSpeed }, uStars:{ value:sky.stars }, uMoon:{ value:sky.moon }, uFlash:{ value:0 }
  };
  const mat = new THREE.ShaderMaterial({
    uniforms:u, side:THREE.BackSide, depthWrite:false, fog:false,
    vertexShader:'varying vec3 vD;void main(){vD=position;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);}',
    fragmentShader:[
      'uniform vec3 uZenith;uniform vec3 uHorizon;uniform vec3 uBand;uniform vec3 uSunCol;uniform vec3 uCloudL;uniform vec3 uCloudS;uniform vec3 uSunDir;',
      'uniform float uSunSize;uniform float uGlow;uniform float uCover;uniform float uCScale;uniform float uTime;uniform float uSpeed;uniform float uStars;uniform float uMoon;uniform float uFlash;varying vec3 vD;',
      'float hash(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}',
      'float noise(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.0-2.0*f);return mix(mix(hash(i),hash(i+vec2(1.0,0.0)),f.x),mix(hash(i+vec2(0.0,1.0)),hash(i+vec2(1.0,1.0)),f.x),f.y);}',
      'float fbm(vec2 p){float s=0.0,a=0.5;for(int i=0;i<5;i++){s+=a*noise(p);p=p*2.03+vec2(1.7,9.2);a*=0.5;}return s;}',
      'void main(){vec3 d=normalize(vD);float h=d.y;vec3 sdir=normalize(uSunDir);float sd=max(dot(d,sdir),0.0);',
      'vec3 col=mix(uHorizon,uZenith,pow(clamp(h,0.0,1.0),0.5));',
      'float band=exp(-abs(h)*6.0)*(0.3+0.7*pow(sd,2.5));col=mix(col,uBand,clamp(band,0.0,1.0));',
      'if(h<0.0)col=mix(uHorizon,uHorizon*0.7,clamp(-h*4.0,0.0,1.0));',
      'col+=uSunCol*(pow(sd,7.0)*0.28+pow(sd,60.0)*0.55)*uGlow;',
      'float disc=smoothstep(1.0-0.0011*uSunSize,1.0-0.0007*uSunSize,sd);',
      'if(uStars>0.5&&h>0.0){vec2 sp=d.xz/(d.y+0.35)*110.0;vec2 cell=floor(sp);float st=step(0.9955,hash(cell));col+=st*vec3(0.85,0.9,1.0)*(0.55+0.45*sin(uTime*2.5+hash(cell+3.1)*30.0))*smoothstep(0.02,0.35,h);}',
      'vec2 uv=d.xz/(h+0.11)*0.5*uCScale+vec2(uTime*uSpeed,uTime*uSpeed*0.35);',
      'float n=fbm(uv*1.8);float cov=smoothstep(1.0-uCover,1.0-uCover+0.16,n);',
      'float lit=fbm(uv*1.8-normalize(sdir.xz+vec2(1e-4))*0.07);float rim=clamp((n-lit)*7.0+0.45,0.0,1.0);',
      'vec3 cc=mix(uCloudS,uCloudL,rim)+uSunCol*pow(sd,5.0)*0.7*rim;',
      'float fade=smoothstep(0.0,0.16,h);col=mix(col,cc,cov*fade*0.96);',
      'col+=disc*uSunCol*(1.0-cov*fade*0.9)*(uMoon>0.5?1.4:3.0);',
      'col+=uFlash*vec3(0.5,0.55,0.7)*(0.4+cov);',
      'gl_FragColor=vec4(col,1.0);',
      '#include <colorspace_fragment>',
      '}'
    ].join('\n')
  });
  const mesh = new THREE.Mesh(new THREE.SphereGeometry(1500, 48, 24), mat);
  mesh.renderOrder = -1; mesh.frustumCulled = false;
  return { mesh, u };
}

/* ---------- partikel: debu/serbuk, kunang-kunang, daun, hujan ---------- */
function teksturTitik(){
  const c = document.createElement('canvas'); c.width = c.height = 64; const x = c.getContext('2d');
  const g = x.createRadialGradient(32, 32, 0, 32, 32, 32); g.addColorStop(0, 'rgba(255,255,255,1)'); g.addColorStop(.35, 'rgba(255,255,255,.55)'); g.addColorStop(1, 'rgba(255,255,255,0)');
  x.fillStyle = g; x.fillRect(0, 0, 64, 64); return new THREE.CanvasTexture(c);
}
function buatPartikel(fx, gradien){
  const grup = new THREE.Group(), sistem = [], titik = teksturTitik();
  for(const f of fx || []){
    const n = f.count, A = f.area || 20, H = f.height || 8;
    if(f.type === 'debu' || f.type === 'kunang'){
      const pos = new Float32Array(n * 3), ph = new Float32Array(n);
      for(let i = 0; i < n; i++){ const a = Math.random() * 6.283, r = Math.sqrt(Math.random()) * A; pos.set([Math.cos(a) * r, .3 + Math.random() * H, Math.sin(a) * r], i * 3); ph[i] = Math.random() * 6.283; }
      const geo = new THREE.BufferGeometry(); geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
      const k = f.type === 'kunang';
      const mat = new THREE.PointsMaterial({ color:f.color, map:titik, size:k ? .34 : .13, transparent:true, opacity:k ? 1 : .75, depthWrite:false, blending:THREE.AdditiveBlending });
      const pts = new THREE.Points(geo, mat); pts.frustumCulled = false; grup.add(pts);
      sistem.push({ jenis:f.type, geo, n, ph, A, H, mat });
    } else if(f.type === 'daun'){
      const im = new THREE.InstancedMesh(new THREE.PlaneGeometry(.22, .13), new THREE.MeshToonMaterial({ gradientMap:gradien, side:THREE.DoubleSide }), n);
      im.frustumCulled = false; const st = [];
      for(let i = 0; i < n; i++){
        im.setColorAt(i, new THREE.Color(f.colors[i % f.colors.length]));
        st.push({ p:new THREE.Vector3((Math.random() - .5) * 2 * A, Math.random() * H, (Math.random() - .5) * 2 * A), r:new THREE.Euler(Math.random() * 6, Math.random() * 6, Math.random() * 6), s:[Math.random() * 3 + 1, Math.random() * 3 + 1, Math.random() * 2], jatuh:.5 + Math.random() * .7, ph:Math.random() * 6.28 });
      }
      grup.add(im); sistem.push({ jenis:'daun', im, st, A, H, laju:f.speed || 1 });
    } else if(f.type === 'hujan'){
      const pos = new Float32Array(n * 6);
      for(let i = 0; i < n; i++){ const x = (Math.random() - .5) * 2 * A, y = Math.random() * H, z = (Math.random() - .5) * 2 * A; pos.set([x, y, z, x, y - .9, z], i * 6); }
      const geo = new THREE.BufferGeometry(); geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
      const l = new THREE.LineSegments(geo, new THREE.LineBasicMaterial({ color:f.color, transparent:true, opacity:.38, depthWrite:false })); l.frustumCulled = false; grup.add(l);
      sistem.push({ jenis:'hujan', geo, n, A, H });
    }
  }
  return { grup, sistem, titik };
}
const _m = new THREE.Matrix4(), _q = new THREE.Quaternion(), _s = new THREE.Vector3(1, 1, 1);
function gerakPartikel(p, dt, t, w){
  for(const s of p.sistem){
    if(s.jenis === 'debu' || s.jenis === 'kunang'){
      const a = s.geo.attributes.position.array, k = s.jenis === 'kunang';
      for(let i = 0; i < s.n; i++){
        const j = i * 3, ph = s.ph[i];
        a[j] += (w.x * .18 + Math.sin(t * .6 + ph) * (k ? .35 : .15)) * dt;
        a[j + 1] += (Math.sin(t * (k ? 1.3 : .5) + ph * 2) * (k ? .25 : .08) + (k ? .02 : .03)) * dt;
        a[j + 2] += (w.y * .18 + Math.cos(t * .5 + ph) * (k ? .35 : .15)) * dt;
        if(a[j + 1] > s.H) a[j + 1] = .3; if(a[j + 1] < .2) a[j + 1] = s.H;
        if(Math.hypot(a[j], a[j + 2]) > s.A){ a[j] *= -.95; a[j + 2] *= -.95; }
      }
      s.geo.attributes.position.needsUpdate = true;
      if(k) s.mat.opacity = .7 + .3 * Math.sin(t * 2.7);
    } else if(s.jenis === 'daun'){
      s.st.forEach((o, i) => {
        o.p.x += (w.x * 1.4 * s.laju + Math.sin(t * 1.3 + o.ph) * .5) * dt;
        o.p.z += (w.y * 1.4 * s.laju + Math.cos(t * 1.1 + o.ph) * .5) * dt;
        o.p.y -= o.jatuh * dt * (s.laju > 1.5 ? .7 : 1);
        o.r.x += o.s[0] * dt; o.r.y += o.s[1] * dt; o.r.z += o.s[2] * dt;
        if(o.p.y < .05 || Math.abs(o.p.x) > s.A || Math.abs(o.p.z) > s.A) o.p.set((Math.random() - .5) * 2 * s.A - w.x * s.A * .5, s.H * (.6 + Math.random() * .4), (Math.random() - .5) * 2 * s.A - w.y * s.A * .5);
        s.im.setMatrixAt(i, _m.compose(o.p, _q.setFromEuler(o.r), _s));
      });
      s.im.instanceMatrix.needsUpdate = true;
    } else if(s.jenis === 'hujan'){
      const a = s.geo.attributes.position.array, vx = w.x * 2.2, vz = w.y * 2.2;
      for(let i = 0; i < s.n; i++){
        const j = i * 6; a[j + 1] -= 24 * dt; a[j] += vx * dt; a[j + 2] += vz * dt;
        if(a[j + 1] < 0){ a[j] = (Math.random() - .5) * 2 * s.A; a[j + 1] = s.H; a[j + 2] = (Math.random() - .5) * 2 * s.A; }
        a[j + 3] = a[j] - vx * .05; a[j + 4] = a[j + 1] - .9; a[j + 5] = a[j + 2] - vz * .05;
      }
      s.geo.attributes.position.needsUpdate = true;
    }
  }
}

/** Unduh file arena (.glb), atau urai isi GLB yang sudah ada di memori (ArrayBuffer). Hasilnya diteruskan ke bangunArena(). */
export function unduhArena(sumber){ return typeof sumber === 'string' ? loader.loadAsync(sumber) : loader.parseAsync(sumber, ''); }

/**
 * Bangun arena dari hasil unduhArena(): material toon, garis tinta, angin, langit, partikel, collider.
 * Arena belum masuk scene; panggil arena.pasang(scene, lampuTitik) untuk menampilkannya.
 * @param {object} gltf
 * @param {{garisTinta?:boolean, tebalGaris?:number, warnaGaris?:string, bayangan?:boolean}} [opsi]
 */
export function bangunArena(gltf, opsi = {}){
  const { garisTinta = true, tebalGaris = .032, warnaGaris = '#1c1824', bayangan = true } = opsi;
  const root = gltf.scene; root.updateMatrixWorld(true);
  const info = root.getObjectByName('ARENA_INFO')?.userData ?? {};
  const env = info.env ?? {};
  const gradien = gradienToon();
  const U = { time:{ value:0 }, wind:{ value:new THREE.Vector2(1, 0) }, outline:{ value:tebalGaris } };
  const lantai = [], colliders = [], spawns = {}, titikPenonton = [], sampah = [gradien], garis = new THREE.Group(), tinta = {};
  const meshes = []; root.traverse(o => { if(o.isMesh) meshes.push(o); });

  for(const o of meshes){
    const grup = o.parent?.name, src = o.material, nama = src.name || '';
    const diLantai = grup === 'GROUND', awan = grup === 'CLOUDS';
    if(diLantai) lantai.push(o);
    const asli = o.geometry;
    const g = asli.index ? asli.toNonIndexed() : asli.clone(); g.computeVertexNormals(); o.geometry = g; sampah.push(g);
    if(nama === 'sinar'){ o.material = bahanSinar(env.sky?.sunColor ?? '#fff0c8', U); o.renderOrder = 2; sampah.push(o.material); continue; }
    const nyala = src.emissive && (src.emissive.r + src.emissive.g + src.emissive.b) > 0;
    const tm = new THREE.MeshToonMaterial({ color:src.vertexColors ? 0xffffff : src.color, gradientMap:gradien, vertexColors:!!src.vertexColors, name:nama });
    if(nyala){ tm.emissive.copy(src.emissive); tm.emissiveIntensity = 1.15; }
    if(awan){ tm.fog = false; tm.emissive.copy(src.color).multiplyScalar(.22); }
    o.material = diLantai || awan || nyala ? tm : tambalAngin(tm, GOYANG[nama] || 0, false, U);
    o.castShadow = bayangan && !diLantai && !awan; o.receiveShadow = bayangan && !awan;
    src.dispose?.();
    sampah.push(o.material);
    if(garisTinta && !diLantai && !awan && !nyala){
      asli.computeVertexNormals();
      if(!tinta[nama]) tinta[nama] = tambalAngin(new THREE.MeshBasicMaterial({ color:warnaGaris, side:THREE.BackSide }), GOYANG[nama] || 0, true, U);
      const gm = new THREE.Mesh(asli, tinta[nama]); gm.matrixAutoUpdate = false; gm.matrix.copy(o.matrixWorld);
      garis.add(gm); sampah.push(asli);
    } else if(asli !== g) asli.dispose();
  }
  Object.values(tinta).forEach(m => sampah.push(m));
  root.add(garis);

  root.traverse(o => {
    if(o.name.startsWith('COL_')){
      const pusat = new THREE.Vector3(), q = new THREE.Quaternion(), ukuran = new THREE.Vector3();
      o.matrixWorld.decompose(pusat, q, ukuran);
      colliders.push({ nama:o.name, pusat, ukuran, sudutY:new THREE.Euler().setFromQuaternion(q, 'YXZ').y, batas:o.name.includes('batas') });
    }
    if(o.name.startsWith('SPAWN_')) spawns[o.name.slice(6)] = { posisi:o.getWorldPosition(new THREE.Vector3()), arahY:new THREE.Euler().setFromQuaternion(o.getWorldQuaternion(new THREE.Quaternion()), 'YXZ').y };
    if(o.name.startsWith('NPC_SPOT_')) titikPenonton.push({ posisi:o.getWorldPosition(new THREE.Vector3()), arahY:new THREE.Euler().setFromQuaternion(o.getWorldQuaternion(new THREE.Quaternion()), 'YXZ').y, jenis:o.userData.kind ?? 'tanah', baris:o.userData.row ?? 0 });
  });

  // data lampu titik, urut dari yang paling dekat pusat arena (lampunya sendiri milik game)
  const nodeLampu = []; root.traverse(o => { if(o.name.startsWith('LIGHT_')) nodeLampu.push(o); });
  const dataLampu = nodeLampu.map(o => {
    const u = o.userData, posisi = o.getWorldPosition(new THREE.Vector3());
    return { posisi, warna:u.color ?? '#ffcc88', kuat:(u.intensity ?? 1.5) * PI, jarak:u.distance ?? 12, d:posisi.length(), ph:Math.random() * 10 };
  }).sort((a, b) => a.d - b.d);

  const langitObj = env.sky ? buatLangit(env.sky) : null;
  if(langitObj) sampah.push(langitObj.mesh.geometry, langitObj.mesh.material);
  if(env.wind) U.wind.value.set(env.wind.dir[0], env.wind.dir[1]).normalize().multiplyScalar(env.wind.strength);
  const fx = buatPartikel(env.fx, gradien);
  const awan = root.getObjectByName('CLOUDS');
  const badai = { tunggu:3, seq:-1, kilat:0, mulai:false };
  let waktu = 0, lampuAktif = [], adegan = null;

  return {
    root, info, env, lantai, colliders, spawns, titikPenonton, dataLampu,
    /** kilat petir saat ini (0..1) */
    get kilat(){ return badai.kilat; },
    /** Tampilkan arena: masukkan ke scene dan nyalakan lampu titik dari kumpulan lampu milik game. */
    pasang(scene, kumpulanLampu = []){
      adegan = scene;
      scene.add(root); if(langitObj) scene.add(langitObj.mesh); scene.add(fx.grup);
      lampuAktif = [];
      kumpulanLampu.forEach((l, i) => {
        const d = dataLampu[i];
        if(!d){ l.intensity = 0; l.userData.dasar = 0; return; }
        l.position.copy(d.posisi); l.color.set(d.warna); l.distance = d.jarak; l.decay = 1.6;
        l.userData.dasar = d.kuat; l.userData.ph = d.ph; l.intensity = d.kuat; lampuAktif.push(l);
      });
    },
    /** Sembunyikan arena (tidak dibuang, bisa dipasang lagi). */
    lepas(){
      if(!adegan) return;
      adegan.remove(root); if(langitObj) adegan.remove(langitObj.mesh); adegan.remove(fx.grup);
      lampuAktif.forEach(l => { l.intensity = 0; l.userData.dasar = 0; }); lampuAktif = []; adegan = null;
    },
    /**
     * Panggil setiap frame. kamera: langit ikut posisi kamera. redup: pengali cahaya lampu (1 = normal).
     * Mengembalikan true pada frame ketika petir baru menyambar (untuk suara guntur).
     */
    update(dt, kamera, redup = 1){
      waktu += dt; U.time.value = waktu;
      if(langitObj){ langitObj.u.uTime.value = waktu; if(kamera) langitObj.mesh.position.copy(kamera.position); }
      if(awan) awan.rotation.y += dt * .0035;
      gerakPartikel(fx, dt, waktu, U.wind.value);
      for(const l of lampuAktif) l.intensity = l.userData.dasar * redup * (.88 + .08 * Math.sin(waktu * 7 + l.userData.ph) + .04 * Math.sin(waktu * 17.3 + l.userData.ph));
      let f = 0, sambar = false;
      if(env.lightning){
        badai.tunggu -= dt;
        if(badai.tunggu <= 0 && badai.seq < 0){ badai.seq = 0; sambar = true; badai.tunggu = env.lightning.min + Math.random() * (env.lightning.max - env.lightning.min); }
        if(badai.seq >= 0){ badai.seq += dt; const s = badai.seq; f = s < .06 ? 1 : s < .12 ? .15 : s < .2 ? .75 : s < .45 ? .75 * (1 - (s - .2) / .25) : 0; if(s > .45) badai.seq = -1; }
      }
      badai.kilat = f;
      if(langitObj) langitObj.u.uFlash.value = f * .9;
      return sambar;
    },
    /** Buang arena dari memori GPU. */
    buang(){
      this.lepas();
      for(const x of sampah) x.dispose?.();
      fx.grup.traverse(o => { o.geometry?.dispose(); o.material?.dispose(); }); fx.titik.dispose();
    }
  };
}

/**
 * Efek sinematik: bloom + color grading (tint bayangan/terang, kontras, saturasi) + vignette.
 * Satu composer untuk seluruh game; atur(env) mengganti suasananya sesuai arena.
 */
export function buatSinematik(renderer, scene, camera){
  const composer = new EffectComposer(renderer);
  composer.addPass(new RenderPass(scene, camera));
  // batasi terang maksimum sebelum bloom: efek jurus aditif yang bertumpuk tidak membuat layar putih total
  const batas = new ShaderPass({
    uniforms:{ tDiffuse:{ value:null }, uMax:{ value:1.5 } },
    vertexShader:'varying vec2 vUv;void main(){vUv=uv;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);}',
    fragmentShader:'uniform sampler2D tDiffuse;uniform float uMax;varying vec2 vUv;void main(){vec4 c=texture2D(tDiffuse,vUv);gl_FragColor=vec4(min(c.rgb,vec3(uMax)),c.a);}'
  });
  composer.addPass(batas);
  const bloom = new UnrealBloomPass(new THREE.Vector2(512, 512), .6, .6, .8);
  composer.addPass(bloom);
  const grade = new ShaderPass({
    uniforms:{ tDiffuse:{ value:null }, uShadow:{ value:new THREE.Color() }, uHigh:{ value:new THREE.Color() },
      uContrast:{ value:1.1 }, uSat:{ value:1.05 }, uVig:{ value:.4 }, uFlash:{ value:0 } },
    vertexShader:'varying vec2 vUv;void main(){vUv=uv;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);}',
    fragmentShader:[
      'uniform sampler2D tDiffuse;uniform vec3 uShadow;uniform vec3 uHigh;uniform float uContrast;uniform float uSat;uniform float uVig;uniform float uFlash;varying vec2 vUv;',
      'vec3 toSRGB(vec3 c){return mix(c*12.92,1.055*pow(c,vec3(1.0/2.4))-0.055,step(vec3(0.0031308),c));}',
      'void main(){vec3 c=toSRGB(max(texture2D(tDiffuse,vUv).rgb,0.0));',
      'float l=dot(c,vec3(0.299,0.587,0.114));c=mix(vec3(l),c,uSat);c=(c-0.5)*uContrast+0.5;',
      'c=mix(c,c*uShadow*1.7,(1.0-smoothstep(0.0,0.55,l))*0.38);c=mix(c,c*uHigh*1.12,smoothstep(0.5,1.0,l)*0.3);',
      'c+=uFlash*vec3(0.55,0.6,0.75);float v=distance(vUv,vec2(0.5));c*=1.0-uVig*smoothstep(0.3,0.86,v);',
      'gl_FragColor=vec4(clamp(c,0.0,1.0),1.0);}'
    ].join('\n')
  });
  composer.addPass(grade);
  function atur(env){
    const gr = env?.grade ?? {};
    grade.uniforms.uShadow.value.setStyle(gr.shadow ?? '#404060', THREE.NoColorSpace);
    grade.uniforms.uHigh.value.setStyle(gr.highlight ?? '#fff0d0', THREE.NoColorSpace);
    grade.uniforms.uContrast.value = gr.contrast ?? 1.1; grade.uniforms.uSat.value = gr.saturation ?? 1.05; grade.uniforms.uVig.value = gr.vignette ?? .4;
    kuatBloom = gr.bloom ?? .6; bloom.threshold = gr.bloomThreshold ?? .8;
  }
  let kuatBloom = .6;
  atur(null);
  return {
    composer, bloom, grade, atur,
    /** kilat: kilat petir 0..1. redup: pengali cahaya game (saat adegan jurus pamungkas bloom ikut diredam). */
    render(kilat = 0, redup = 1){ grade.uniforms.uFlash.value = kilat * .22; bloom.strength = kuatBloom * (.45 + .55 * redup); composer.render(); },
    setSize(w, h){ composer.setSize(w, h); }
  };
}

/** Dorong lingkaran berjari-jari `radius` di bidang XZ keluar dari semua collider. Mengubah `posisi` langsung. */
export function dorongKeluar(posisi, radius, colliders){
  for(const c of colliders){
    if(posisi.y > c.pusat.y + c.ukuran.y / 2) continue;
    const dx = posisi.x - c.pusat.x, dz = posisi.z - c.pusat.z;
    const cos = Math.cos(c.sudutY), sin = Math.sin(c.sudutY);
    const lx = dx * cos - dz * sin, lz = dx * sin + dz * cos;
    const hx = c.ukuran.x / 2, hz = c.ukuran.z / 2;
    const ox = lx - Math.max(-hx, Math.min(hx, lx)), oz = lz - Math.max(-hz, Math.min(hz, lz));
    const d2 = ox * ox + oz * oz;
    if(d2 >= radius * radius) continue;
    let nx, nz, dalam;
    if(d2 > 1e-8){ const d = Math.sqrt(d2); nx = ox / d; nz = oz / d; dalam = radius - d; }
    else { const kx = hx - Math.abs(lx), kz = hz - Math.abs(lz); if(kx < kz){ nx = Math.sign(lx) || 1; nz = 0; dalam = kx + radius; } else { nx = 0; nz = Math.sign(lz) || 1; dalam = kz + radius; } }
    posisi.x += (nx * cos + nz * sin) * dalam;
    posisi.z += (-nx * sin + nz * cos) * dalam;
  }
  return posisi;
}

/** true kalau titik (x, y, z) berada di dalam salah satu collider (dilebarkan c.padKamera atau `pad`). Dipakai kamera. */
export function diDalamCollider(x, y, z, colliders, padAwal = 0){
  for(const c of colliders){
    if(c.batas) continue;
    const pad = c.padKamera ?? padAwal;
    if(y > c.pusat.y + c.ukuran.y / 2 + pad || y < c.pusat.y - c.ukuran.y / 2 - pad) continue;
    const dx = x - c.pusat.x, dz = z - c.pusat.z, cos = Math.cos(c.sudutY), sin = Math.sin(c.sudutY);
    if(Math.abs(dx * cos - dz * sin) < c.ukuran.x / 2 + pad && Math.abs(dx * sin + dz * cos) < c.ukuran.z / 2 + pad) return true;
  }
  return false;
}
