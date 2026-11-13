/* Visible defaults remain available if the motion module cannot load. */
document.documentElement.classList.add('js');
if(!matchMedia('(prefers-reduced-motion: reduce)').matches){
 document.documentElement.classList.add('m-enter');
 setTimeout(()=>document.documentElement.classList.add('m-enter-done'),700);
}
