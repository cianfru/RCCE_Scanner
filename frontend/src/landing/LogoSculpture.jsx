import { useEffect, useRef, useState } from 'react';
import { logoOutline } from './logoOutline.js';

export default function LogoSculpture({ active }) {
  const mount = useRef(null);
  const control = useRef(null);
  const activeRef = useRef(active);
  const [ready, setReady] = useState(false);
  useEffect(() => { activeRef.current = active; control.current?.(); }, [active]);
  useEffect(() => {
    let disposed = false, renderer, observer, frame, environment, geometry, face, edge, texture, scene, camera, sculpture;
    let last = 0;
    const render = () => {
      cancelAnimationFrame(frame);
      if (disposed || !renderer) return;
      renderer.render(scene, camera);
      if (activeRef.current) { last = performance.now(); frame = requestAnimationFrame(tick); }
    };
    const tick = now => {
      if (disposed || !activeRef.current) return;
      sculpture.rotation.y += Math.min((now-last)/1000, .05) * Math.PI / 18;
      last = now;
      renderer.render(scene, camera);
      frame = requestAnimationFrame(tick);
    };
    async function init() {
      try {
        const [THREE, {SVGLoader}, {RoomEnvironment}] = await Promise.all([import('three'), import('three/addons/loaders/SVGLoader.js'), import('three/addons/environments/RoomEnvironment.js')]);
        if (disposed) return;
        renderer = new THREE.WebGLRenderer({alpha:true, antialias:true, powerPreference:'low-power'});
        renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
        renderer.setClearColor(0, 0);
        renderer.toneMapping = THREE.ACESFilmicToneMapping;
        renderer.toneMappingExposure = 1.0;
        mount.current.appendChild(renderer.domElement);
        renderer.domElement.setAttribute('aria-hidden','true');
        scene = new THREE.Scene();
        camera = new THREE.PerspectiveCamera(34, 1, .1, 100);
        camera.position.set(0, .05, 6.4);
        const pmrem = new THREE.PMREMGenerator(renderer);
        const room = new RoomEnvironment();
        environment = pmrem.fromScene(room, .04);
        scene.environment = environment.texture;
        room.dispose(); pmrem.dispose();
        const light = new THREE.DirectionalLight('#c6fff1', 1.5); light.position.set(-3,4,5); scene.add(light);
        const rim = new THREE.DirectionalLight('#91b9e8', 2); rim.position.set(4,1,-3); scene.add(rim);
        const svg = new SVGLoader().parse(`<svg xmlns="http://www.w3.org/2000/svg"><path d="${logoOutline}" fill-rule="evenodd"/></svg>`);
        const shapes = svg.paths.flatMap(path => SVGLoader.createShapes(path));
        geometry = new THREE.ExtrudeGeometry(shapes,{depth:65,bevelEnabled:true,bevelThickness:12,bevelSize:10,bevelSegments:6,steps:1,curveSegments:36});
        const positions = geometry.attributes.position, uv = geometry.attributes.uv;
        for(let i=0;i<positions.count;i++) {
          const x=positions.getX(i), y=positions.getY(i), z=positions.getZ(i);
          uv.setXY(i,x/1672,1-y/941);

        }
        geometry.scale(.005,-.005,.005); geometry.center(); geometry.computeVertexNormals();
        face = new THREE.MeshPhysicalMaterial({color:'#97fce4',metalness:.35,roughness:.35,clearcoat:1,clearcoatRoughness:.19});
        edge = new THREE.MeshPhysicalMaterial({color:'#66bca7',metalness:.9,roughness:.22,clearcoat:1});
        sculpture = new THREE.Mesh(geometry,[face,edge]);
        sculpture.rotation.set(.06,-.25,-.055); scene.add(sculpture);
        const resize = () => { if(disposed) return; const {width,height}=mount.current.getBoundingClientRect();renderer.setSize(width,height);camera.aspect=width/Math.max(height,1);camera.updateProjectionMatrix();render(); };
        observer = new ResizeObserver(resize); observer.observe(mount.current);
        control.current = render;
        renderer.domElement.addEventListener('webglcontextlost',()=>{cancelAnimationFrame(frame);setReady(false);});
        resize(); setReady(true);
        // Retain the original ribbon's surface detail on the front and back of the solid.
        new THREE.TextureLoader().load('/brand/reflex-logo-surface.png', loaded => {
          if(disposed) {loaded.dispose();return;}
          texture=loaded; texture.colorSpace=THREE.SRGBColorSpace; face.map=texture; face.color.set('#f5fefd');face.needsUpdate=true;render();
        });
      } catch { if(!disposed) setReady(false); }
    }
    init();
    return () => { disposed=true; control.current=null;cancelAnimationFrame(frame);observer?.disconnect();geometry?.dispose();face?.dispose();edge?.dispose();texture?.dispose();environment?.dispose();renderer?.dispose();renderer?.domElement.remove(); };
  }, []);
  return <div ref={mount} className="r-sculpture" data-rendered={ready}>
    {!ready && <img src="/brand/reflex-ribbon-transparent.svg" width="535" height="555" alt=""/>}
  </div>;
}
