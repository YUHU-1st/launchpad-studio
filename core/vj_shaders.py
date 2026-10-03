"""Original procedural visuals, rendered in OpenGL 3.3 with no external footage."""

VERTEX = '''#version 330
out vec2 uv;
void main(){
    vec2 p=vec2((gl_VertexID<<1)&2,gl_VertexID&2);
    uv=p; gl_Position=vec4(p*2.0-1.0,0.0,1.0);
}
'''

FRAGMENT = '''#version 330
in vec2 uv;
out vec4 frag;
uniform vec2 resolution;
uniform float clock, energy, bass, treble, beat, speed, intensity, detail, transition;
uniform int scene, previous, alpha;
uniform vec3 lowColor, highColor;
uniform float bands[32];
const float PI=3.14159265359;
float hash(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}
float noise(vec2 p){vec2 i=floor(p),f=fract(p); f=f*f*(3.0-2.0*f); return mix(mix(hash(i),hash(i+vec2(1,0)),f.x),mix(hash(i+vec2(0,1)),hash(i+vec2(1)),f.x),f.y);}
float fbm(vec2 p){float n=0.0,a=.5; for(int i=0;i<4;i++){n+=a*noise(p);p=mat2(1.6,-1.2,1.2,1.6)*p+4.1;a*=.5;}return n;}
mat2 rot(float a){return mat2(cos(a),-sin(a),sin(a),cos(a));}
vec3 palette(float h){return mix(lowColor,highColor,.5+.5*sin(h*6.283))+vec3(.05,.04,.08)*(.5+.5*cos(h*9.));}
float glow(float d,float width){return width/(abs(d)+width);}
vec3 drawScene(int s,vec2 p,float t){
    float r=length(p),ang=atan(p.y,p.x),audio=.3+energy, kick=beat*.18;
    vec3 col=vec3(0);
    if(s==0){ // twisting neon tunnel with spectrum spokes
        p=rot(t*.08+sin(t*.27)*.2)*p;
        float z=1.0/max(r,.04)+t*(.7+bass*1.4);
        float ring=abs(fract(z*.55)-.5);
        float spokes=abs(sin(atan(p.y,p.x)*8.+z*.45));
        float power=glow(ring,.018+.014*detail)+glow(spokes,.012)*.4;
        col=palette(z*.055+t*.015)*power*smoothstep(.02,.22,r)*(audio+kick);
        col+=highColor*pow(max(0.,1.-r),14.)*(.12+beat*.45);
    }else if(s==1){ // laser stage in perspective
        vec2 q=rot(sin(t*.2)*.3)*p;
        float z=1./max(.12,abs(q.y)+.13), grid=abs(fract(q.x*z*2.5*detail+t*.12)-.5);
        float rows=abs(fract(z+t*(.8+bass))-.5);
        col=palette(q.y*.2+t*.035)*(glow(grid,.016)+glow(rows,.012))*.48*audio;
        for(int i=0;i<6;i++){
            float a=t*.17+float(i)*PI/3.;float ray=abs(dot(q,vec2(cos(a),sin(a)))-sin(t+float(i))*.22);
            col+=palette(float(i)*.13)*glow(ray,.0025+.002*beat)*(energy*.7+.2);
        }
    }else if(s==2){ // layered star flight / glowing particle field
        for(int i=0;i<7;i++){
            float depth=fract(float(i)/7.+t*.13*(.3+energy));
            float scale=mix(12.,.5,depth);
            vec2 q=rot(t*.07)*p*scale+vec2(float(i)*17.3);
            vec2 cell=floor(q),f=fract(q)-.5;
            vec2 point=(vec2(hash(cell),hash(cell+8.3))-.5)*.65;
            float d=length((f-point)*vec2(1.,.7));
            float spark=pow(max(0.,1.-d),42.)*(.4+depth)*(.5+hash(cell+4.));
            col+=palette(hash(cell)*.6+t*.02)*spark*(.6+energy*2.+beat);
        }
        col+=palette(ang*.1+t*.03)*pow(max(0.,1.-r*.55),5.)*.04;
    }else if(s==3){ // nebula with flowing fractal ribbons
        vec2 q=p*.9*detail;
        float n=fbm(q*2.+vec2(t*.07,-t*.05));
        float m=fbm(q*3.+n*3.+vec2(-t*.08,t*.04));
        float cloud=pow(m,2.)*(.35+energy*1.4);
        float ribbon=glow(sin(n*14.+m*10.-t*.45),.05+.05*bass);
        col=palette(m*.8+n*.4+t*.013)*(cloud+ribbon*.22);
        col+=highColor*pow(n*m,3.)*3.*(1.+beat*.4);
    }else if(s==4){ // angular kaleidoscope, fine geometry and bloom
        float sector=PI/(5.+floor(detail*3.));
        float a=abs(mod(ang+t*.14,sector*2.)-sector);
        vec2 q=vec2(cos(a),sin(a))*r;
        float n=sin(q.x*9.*detail-t)*cos(q.y*12.*detail+t*.6);
        float cell=sin((q.x+q.y)*14.-t*.8)+cos(r*10.-t*1.2);
        col=palette(n*.3+r*.2+t*.024)*(glow(cell,.055)+glow(n,.04)*.5)*audio;
        col*=.6+.4*smoothstep(1.8,.1,r);
    }else if(s==5){ // liquid metal: curved highlights and coloured reflections
        float n=fbm(p*2.2*detail+vec2(t*.07));
        float f=sin(p.x*3.+n*5.+t*.35)+cos(p.y*4.+n*3.-t*.3);
        float highlight=pow(.5+.5*sin(f*4.+n*9.),8.);
        vec3 metal=mix(palette(f*.23+t*.02),vec3(.85,.95,1.),highlight*.75);
        col=metal*(.08+highlight*.9+glow(f,.08)*.2)*(.45+energy);
    }else if(s==6){ // synthwave horizon, retro sun and audio skyline
        float horizon=.12;
        if(p.y<horizon){
            float depth=1./max(.08,horizon-p.y), gx=abs(fract(p.x*depth*2.)-.5),gy=abs(fract(depth-t*.8)-.5);
            col=palette(t*.01+.65)*(glow(gx,.025)+glow(gy,.02))*.3*audio;
        }
        vec2 sun=p-vec2(0.,.35);float sr=length(sun);
        float disc=(1.-smoothstep(.37,.385,sr))*(.7+.3*sin(p.y*80.+t*.2));
        col+=palette(p.y*.6+t*.01)*disc*(.5+energy*.6);
        int band=int(clamp((p.x+1.6)/3.2*32.,0.,31.));
        float skyline=step(abs(p.y-horizon),bands[band]*.34)*step(abs(p.x),1.6);
        col+=highColor*skyline*.4;
    }else{ // monochrome techno lattice with asymmetric motion
        vec2 q=rot(t*.06)*p*(4.+detail*3.);
        vec2 id=floor(q);vec2 f=fract(q)-.5;
        float edge=abs(max(abs(f.x),abs(f.y))-(.22+sin(hash(id)*6.+t*1.3)*.13));
        float gate=.25+.75*step(.45,hash(id+floor(t*.3)));
        col=palette(hash(id)*.12+t*.01)*glow(edge,.011)*gate*(.3+energy+beat*.3);
        col+=highColor*glow(p.x+sin(p.y*3.+t)*.18,.006)*treble;
    }
    return max(vec3(0),col);
}
void main(){
    vec2 p=(uv-.5)*vec2(resolution.x/resolution.y,1.)*2.;
    float t=clock*speed;
    vec3 color=transition>=1.?drawScene(scene,p,t):mix(drawScene(previous,p,t),drawScene(scene,p,t),smoothstep(0.,1.,transition));
    color*=intensity*(.85+.15*beat);
    color=1.-exp(-color*1.5);
    float opacity=alpha==1?smoothstep(.015,.35,max(max(color.r,color.g),color.b)):1.;
    frag=vec4(color*opacity,opacity);
}
'''

PRESENT = '''#version 330
in vec2 uv;out vec4 frag;
uniform sampler2D image;
uniform vec2 sourceSize,targetSize;
void main(){
    float sourceAspect=sourceSize.x/sourceSize.y,targetAspect=targetSize.x/targetSize.y;
    vec2 scale=vec2(max(1.,targetAspect/sourceAspect),max(1.,sourceAspect/targetAspect));
    vec2 q=(uv-.5)*scale+.5;
    frag=any(lessThan(q,vec2(0)))||any(greaterThan(q,vec2(1)))?vec4(0,0,0,0):texture(image,q);
}
'''

MAP = '''#version 330
in vec2 uv;out vec4 frag;
uniform sampler2D image;
uniform vec2 cellSize;
void main(){
    vec3 avg=vec3(0),peak=vec3(0);
    for(int y=0;y<8;y++)for(int x=0;x<8;x++){
        vec3 c=texture(image,uv+(vec2(x,y)/7.-.5)*cellSize*.95).rgb;
        avg+=c/64.;peak=max(peak,c);
    }
    frag=vec4(mix(avg,peak,.55),1.);
}
'''
