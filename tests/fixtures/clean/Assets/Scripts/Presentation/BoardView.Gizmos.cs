using UnityEngine;

namespace Game.Presentation
{
    /// <summary>
    /// The second part of a partial class, in a file named Type.Part.cs - the usual way to keep one
    /// concern of a large class, such as editor-only or debug-only code, in a file of its own. The
    /// file/type rule must accept it, because the type it declares is partial.
    /// </summary>
    public partial class BoardView
    {
        private void OnDrawGizmos()
        {
            Gizmos.DrawWireCube(transform.position, Vector3.one);
        }
    }
}
