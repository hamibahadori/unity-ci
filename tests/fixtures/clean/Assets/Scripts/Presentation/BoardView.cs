using UnityEngine;

namespace Game.Presentation
{
    /// <summary>
    /// Uses UnityEngine legitimately — this assembly is not engine-free, so the purity check must
    /// leave it alone. That scoping is the thing worth protecting.
    ///
    /// Partial, with a second part in BoardView.Gizmos.cs, so the file/type rule is exercised on a
    /// type split across files.
    /// </summary>
    public partial class BoardView : MonoBehaviour
    {
        [SerializeField] private Transform _boardRoot;

        public Transform BoardRoot => _boardRoot;
    }
}
