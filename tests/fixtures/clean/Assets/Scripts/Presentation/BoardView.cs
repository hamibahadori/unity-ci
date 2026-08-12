using UnityEngine;

namespace Game.Presentation
{
    /// <summary>
    /// Uses UnityEngine legitimately — this assembly is not engine-free, so the purity check must
    /// leave it alone. That scoping is the thing worth protecting.
    /// </summary>
    public class BoardView : MonoBehaviour
    {
        [SerializeField] private Transform _boardRoot;

        public Transform BoardRoot => _boardRoot;
    }
}
