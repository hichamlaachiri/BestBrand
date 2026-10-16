import React, { useState, useEffect } from 'react';
import { 
  ShoppingBag, 
  Search, 
  X, 
  Plus, 
  Minus, 
  ArrowRight, 
  CheckCircle2, 
  RotateCcw, 
  ShieldCheck, 
  Layers
} from 'lucide-react';
import './App.css';

const STORE_API_URL = '/wp-json/wc/store/v1/products';

export default function App() {
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedCategory, setSelectedCategory] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedProduct, setSelectedProduct] = useState(null);
  const [selectedSize, setSelectedSize] = useState('');
  const [activeImgIndex, setActiveImgIndex] = useState(0);
  const [cart, setCart] = useState([]);
  const [isCartOpen, setIsCartOpen] = useState(false);
  const [toast, setToast] = useState('');

  // Fetch live products from WooCommerce Store API
  useEffect(() => {
    async function fetchCatalog() {
      try {
        setLoading(true);
        const res = await fetch(`${STORE_API_URL}?per_page=50`);
        if (res.ok) {
          const data = await res.json();
          const formatted = data.map(p => {
            const sizeAttr = p.attributes?.find(a => a.name.toLowerCase().includes('taille') || a.name.toLowerCase().includes('size'));
            const sizes = sizeAttr?.terms?.map(t => t.name) || ['S', 'M', 'L', 'XL'];
            const rawPrice = p.prices?.price ? (parseInt(p.prices.price) / 100).toFixed(2) : '790.00';
            const cleanTitle = p.name.replace(/&#8211;/g, '-').replace(/&#8217;/g, "'").replace(/\&amp;/g, '&');
            
            return {
              id: p.id,
              name: cleanTitle,
              sku: p.sku || `PROD-${p.id}`,
              price: rawPrice,
              images: p.images?.map(img => img.src) || [],
              categories: p.categories?.map(c => c.name.toLowerCase()) || [],
              sizes: sizes,
              inStock: p.is_in_stock ?? true,
              permalink: p.permalink
            };
          });
          setProducts(formatted);
        } else {
          loadFallbackProducts();
        }
      } catch (err) {
        console.warn('Store API connection blip, loading fallback products:', err);
        loadFallbackProducts();
      } finally {
        setLoading(false);
      }
    }

    fetchCatalog();
  }, []);

  function loadFallbackProducts() {
    setProducts([
      {
        id: 79,
        name: "Nike Tech Men's Fleece Windrunner Full-Zip Jacket - Thunder Blue/Comet Blue",
        sku: "HV0949-438",
        price: "890.00",
        images: [
          "https://ghostwhite-chamois-737385.hostingersite.com/wp-content/uploads/2026/10/HV0949_438_S_1.jpg",
          "https://ghostwhite-chamois-737385.hostingersite.com/wp-content/uploads/2026/10/HV0949_438_S_2.jpg",
          "https://ghostwhite-chamois-737385.hostingersite.com/wp-content/uploads/2026/10/HV0949_438_S_3.jpg"
        ],
        categories: ["hoodies", "sportswear"],
        sizes: ["S", "M", "L", "XL"],
        inStock: true
      },
      {
        id: 68,
        name: "Nike Tech Fleece Windrunner Full-Zip Hoodie - Armory Navy",
        sku: "IH4302-437",
        price: "790.00",
        images: [
          "https://ghostwhite-chamois-737385.hostingersite.com/wp-content/uploads/2026/10/IH4302_437_S_1-scaled.jpg",
          "https://ghostwhite-chamois-737385.hostingersite.com/wp-content/uploads/2026/10/IH4302_437_S_2.jpg",
          "https://ghostwhite-chamois-737385.hostingersite.com/wp-content/uploads/2026/10/IH4302_437_S_3.jpg"
        ],
        categories: ["hoodies", "sportswear"],
        sizes: ["S", "M", "L", "XL"],
        inStock: true
      },
      {
        id: 55,
        name: "Nike Tech Fleece Tracksuit",
        sku: "HI4302-012",
        price: "790.00",
        images: [
          "https://ghostwhite-chamois-737385.hostingersite.com/wp-content/uploads/2026/10/HI4302_012_1-4.jpg",
          "https://ghostwhite-chamois-737385.hostingersite.com/wp-content/uploads/2026/10/HI4302_012_2-4.jpg"
        ],
        categories: ["sportswear", "hoodies"],
        sizes: ["XS", "S", "M", "L"],
        inStock: true
      }
    ]);
  }

  // Filter products by category and search
  const filteredProducts = products.filter(p => {
    const matchesCategory = selectedCategory === 'all' 
      ? true 
      : p.categories.some(c => c.includes(selectedCategory));
      
    const matchesSearch = p.name.toLowerCase().includes(searchQuery.toLowerCase()) || 
                          p.sku.toLowerCase().includes(searchQuery.toLowerCase());
                          
    return matchesCategory && matchesSearch;
  });

  // Open modal for a product
  function openProductModal(prod) {
    setSelectedProduct(prod);
    setSelectedSize(prod.sizes?.[0] || 'M');
    setActiveImgIndex(0);
  }

  // Add to Bag
  function handleAddToBag(prod, size) {
    if (!size) {
      alert('Veuillez sélectionner une taille.');
      return;
    }
    const cartItemId = `${prod.id}-${size}`;
    setCart(prev => {
      const existing = prev.find(item => item.cartItemId === cartItemId);
      if (existing) {
        return prev.map(item => 
          item.cartItemId === cartItemId ? { ...item, quantity: item.quantity + 1 } : item
        );
      } else {
        return [...prev, { cartItemId, product: prod, size, quantity: 1 }];
      }
    });

    setToast(`Ajouté au panier : ${prod.name.slice(0, 26)}... (${size})`);
    setTimeout(() => setToast(''), 3500);
    setIsCartOpen(true);
  }

  // Cart Qty updates
  function updateCartQty(cartItemId, delta) {
    setCart(prev => prev.map(item => {
      if (item.cartItemId === cartItemId) {
        const newQty = item.quantity + delta;
        return newQty > 0 ? { ...item, quantity: newQty } : null;
      }
      return item;
    }).filter(Boolean));
  }

  const totalCartCount = cart.reduce((acc, item) => acc + item.quantity, 0);
  const totalCartPrice = cart.reduce((acc, item) => acc + (parseFloat(item.product.price) * item.quantity), 0).toFixed(2);

  return (
    <div className="app-layout">
      {/* Toast Notification */}
      {toast && (
        <div className="toast-msg animate-slide-in">
          <CheckCircle2 size={20} color="#ffffff" />
          <span>{toast}</span>
        </div>
      )}

      {/* Top Banner Bar */}
      <div style={{ background: '#070709', borderBottom: '1px solid var(--border-subtle)', padding: '0.45rem 1rem', textAlign: 'center', fontSize: '0.78rem', fontWeight: 600, color: 'var(--text-secondary)', letterSpacing: '0.04em' }}>
        BEST BRAND OFFICIAL STORE • SYNCHRONISATION EN DIRECT DU STOCK SMART GESTCAISSE • LIVRAISON PARTOUT AU MAROC
      </div>

      {/* Sticky Navigation Bar */}
      <header className="navbar-sticky glass-nav">
        <div className="container-max nav-inner">
          <div className="brand-logo" onClick={() => { setSelectedCategory('all'); setSearchQuery(''); }}>
            <img src="/logo.jpg" alt="BEST BRAND" className="brand-logo-img" />
            <h1>BEST BRAND</h1>
          </div>

          <nav>
            <ul className="nav-links">
              <li>
                <button 
                  className={selectedCategory === 'all' ? 'active' : ''} 
                  onClick={() => setSelectedCategory('all')}
                >
                  ALL RELEASES
                </button>
              </li>
              <li>
                <button 
                  className={selectedCategory === 'hoodies' ? 'active' : ''} 
                  onClick={() => setSelectedCategory('hoodies')}
                >
                  HOODIES & TECH FLEECE
                </button>
              </li>
              <li>
                <button 
                  className={selectedCategory === 'sneakers' ? 'active' : ''} 
                  onClick={() => setSelectedCategory('sneakers')}
                >
                  SNEAKERS
                </button>
              </li>
              <li>
                <button 
                  className={selectedCategory === 'sportswear' ? 'active' : ''} 
                  onClick={() => setSelectedCategory('sportswear')}
                >
                  SPORTSWEAR
                </button>
              </li>
            </ul>
          </nav>

          <div className="nav-actions">
            <div className="search-bar-wrap">
              <Search className="search-icon" />
              <input 
                type="text" 
                placeholder="Search models, SKU..." 
                className="search-input"
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
              />
            </div>

            <button className="cart-btn" onClick={() => setIsCartOpen(true)} aria-label="View Shopping Bag">
              <ShoppingBag size={20} />
              {totalCartCount > 0 && <span className="cart-count-badge">{totalCartCount}</span>}
            </button>
          </div>
        </div>
      </header>

      {/* Hero Athletic Monochrome Banner */}
      <section className="hero-section">
        <div className="container-max">
          <div className="hero-content animate-fade-in">
            <div className="hero-pill-tag">
              <span>SMARTBASE-2026 INVENTORY VERIFIED</span>
            </div>
            <h2 className="title-athletic hero-title">
              CROWNED BY EXCELLENCE.
              <span>SUPREME SPORTSWEAR.</span>
            </h2>
            <p className="hero-subtitle">
              L'excellence du sportswear et du streetwear de marque. Tech Fleece haute précision, pièces d'exception et sneakers vérifiés, reliés en temps réel aux stocks physiques de votre caisse.
            </p>
            <div className="hero-cta-group">
              <button className="btn-primary" onClick={() => setSelectedCategory('hoodies')}>
                DÉCOUVRIR TECH FLEECE <ArrowRight size={18} />
              </button>
              <button className="btn-secondary" onClick={() => setSelectedCategory('all')}>
                COLLECTION COMPLÈTE ({products.length})
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* Main Content & Products */}
      <main className="container-max">
        {/* Category Filter Pills */}
        <div className="filter-bar">
          <div className="category-tabs">
            <button 
              className={`cat-tab ${selectedCategory === 'all' ? 'active' : ''}`}
              onClick={() => setSelectedCategory('all')}
            >
              All Items ({products.length})
            </button>
            <button 
              className={`cat-tab ${selectedCategory === 'hoodies' ? 'active' : ''}`}
              onClick={() => setSelectedCategory('hoodies')}
            >
              Hoodies & Windrunners
            </button>
            <button 
              className={`cat-tab ${selectedCategory === 'sneakers' ? 'active' : ''}`}
              onClick={() => setSelectedCategory('sneakers')}
            >
              Sneakers
            </button>
            <button 
              className={`cat-tab ${selectedCategory === 'sportswear' ? 'active' : ''}`}
              onClick={() => setSelectedCategory('sportswear')}
            >
              Sportswear
            </button>
          </div>

          <div style={{ fontSize: '0.82rem', color: 'var(--text-muted)', fontWeight: 700, letterSpacing: '0.04em' }}>
            AFFICHAGE : <span style={{ color: '#ffffff' }}>{filteredProducts.length} ARTICLES</span> EN STOCK
          </div>
        </div>

        {/* Products Grid */}
        {loading ? (
          <div style={{ padding: '6rem 0', textAlign: 'center', color: 'var(--text-secondary)' }}>
            <div style={{ display: 'inline-block', width: 40, height: 40, border: '3px solid rgba(255,255,255,0.1)', borderTopColor: '#ffffff', borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
            <p style={{ marginTop: '1.25rem', fontWeight: 600, color: 'var(--text-secondary)' }}>Connexion au catalogue live...</p>
          </div>
        ) : filteredProducts.length === 0 ? (
          <div style={{ padding: '6rem 0', textAlign: 'center', color: 'var(--text-secondary)' }}>
            <Layers size={48} style={{ opacity: 0.3, marginBottom: '1rem' }} />
            <h3>Aucun produit trouvé</h3>
            <p style={{ color: 'var(--text-muted)' }}>Essayez de modifier votre recherche ou filtre.</p>
          </div>
        ) : (
          <div className="products-grid">
            {filteredProducts.map(prod => (
              <div 
                key={prod.id} 
                className="product-card"
                onClick={() => openProductModal(prod)}
              >
                <div className="card-media">
                  <div className="card-badge">
                    <span className="badge-tag new">NEW IN</span>
                  </div>
                  <img 
                    src={prod.images[0] || 'https://images.unsplash.com/photo-1556906781-9a412961c28c?w=600&auto=format&fit=crop&q=80'} 
                    alt={prod.name}
                    className="card-img"
                    loading="lazy"
                  />
                </div>

                <div className="card-details">
                  <span className="card-brand">NIKE / BEST BRAND</span>
                  <h3 className="card-title">{prod.name}</h3>

                  <div className="card-sizes-preview">
                    {prod.sizes.slice(0, 4).map(s => (
                      <span key={s} className="size-tag-mini">{s}</span>
                    ))}
                    {prod.sizes.length > 4 && <span className="size-tag-mini">+{prod.sizes.length - 4}</span>}
                  </div>

                  <div className="card-price-row">
                    <div className="card-price">
                      {prod.price} <small>MAD</small>
                    </div>
                    <button 
                      className="btn-secondary" 
                      style={{ padding: '0.45rem 0.95rem', fontSize: '0.8rem' }}
                      onClick={(e) => {
                        e.stopPropagation();
                        openProductModal(prod);
                      }}
                    >
                      DÉTAILS
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </main>

      {/* Detailed Product Modal (Nike Style with size selector pills) */}
      {selectedProduct && (
        <div className="modal-overlay" onClick={() => setSelectedProduct(null)}>
          <div className="modal-container animate-fade-in" onClick={e => e.stopPropagation()}>
            <button className="modal-close-btn" onClick={() => setSelectedProduct(null)}>
              <X size={20} />
            </button>

            <div className="modal-grid">
              {/* Gallery Column */}
              <div className="modal-gallery">
                <div className="main-preview-img-wrap">
                  <img 
                    src={selectedProduct.images[activeImgIndex] || selectedProduct.images[0]} 
                    alt={selectedProduct.name}
                    className="main-preview-img"
                  />
                </div>
                {selectedProduct.images.length > 1 && (
                  <div className="thumbnail-row">
                    {selectedProduct.images.map((imgUrl, idx) => (
                      <button 
                        key={idx}
                        className={`thumb-btn ${activeImgIndex === idx ? 'active' : ''}`}
                        onClick={() => setActiveImgIndex(idx)}
                      >
                        <img src={imgUrl} alt="Thumbnail preview" />
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {/* Info & Options Column */}
              <div className="modal-info-col">
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                  <span className="badge-tag sync">
                    SMARTBASE-2026 IN STOCK
                  </span>
                </div>

                <h2 className="modal-title">{selectedProduct.name}</h2>
                <div className="modal-sku">SKU Modèle : {selectedProduct.sku}</div>

                <div className="modal-price">
                  {selectedProduct.price} <small style={{ fontSize: '1rem', color: 'var(--text-muted)' }}>MAD</small>
                </div>

                {/* Size Selector Pills */}
                <div className="size-select-label">
                  <span>SÉLECTIONNEZ VOTRE TAILLE (POINTURE / TAILLE)</span>
                  <span style={{ color: 'var(--text-secondary)', cursor: 'pointer', fontSize: '0.8rem', fontWeight: 600 }}>Guide des tailles</span>
                </div>

                <div className="size-pills-wrap">
                  {selectedProduct.sizes.map(s => (
                    <button
                      key={s}
                      className={`size-pill ${selectedSize === s ? 'active' : ''}`}
                      onClick={() => setSelectedSize(s)}
                    >
                      {s}
                    </button>
                  ))}
                </div>

                {/* Add to Bag CTA */}
                <button 
                  className="btn-primary" 
                  style={{ width: '100%', padding: '1.15rem', fontSize: '1.02rem', marginBottom: '1.5rem' }}
                  onClick={() => {
                    handleAddToBag(selectedProduct, selectedSize);
                    setSelectedProduct(null);
                  }}
                >
                  <ShoppingBag size={20} /> AJOUTER AU PANIER • {selectedProduct.price} MAD
                </button>

                {/* Feature Highlights */}
                <div style={{ borderTop: '1px solid var(--border-subtle)', paddingTop: '1.25rem', display: 'flex', flexDirection: 'column', gap: '0.75rem', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                    <ShieldCheck size={18} color="#ffffff" />
                    <span>Produit 100% Authentique & Vérifié en Magasin</span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                    <RotateCcw size={18} color="#ffffff" />
                    <span>Échange de taille garanti sous 7 jours</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Slide-out Cart Drawer */}
      {isCartOpen && (
        <div className="cart-drawer-overlay" onClick={() => setIsCartOpen(false)}>
          <div className="cart-drawer animate-slide-in" onClick={e => e.stopPropagation()}>
            <div className="cart-header">
              <h2>PANIER BEST BRAND ({totalCartCount})</h2>
              <button className="cart-btn" onClick={() => setIsCartOpen(false)}>
                <X size={20} />
              </button>
            </div>

            <div className="cart-items-scroll">
              {cart.length === 0 ? (
                <div style={{ padding: '4rem 1rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                  <ShoppingBag size={48} style={{ opacity: 0.25, marginBottom: '1rem' }} />
                  <p>Votre panier est vide pour le moment.</p>
                </div>
              ) : (
                cart.map(item => (
                  <div key={item.cartItemId} className="cart-item-row">
                    <img 
                      src={item.product.images[0]} 
                      alt={item.product.name} 
                      className="cart-item-thumb"
                    />
                    <div className="cart-item-info">
                      <h4 className="cart-item-title">{item.product.name}</h4>
                      <span className="cart-item-meta">Taille : {item.size} • {item.product.sku}</span>
                      <div className="cart-item-actions">
                        <strong style={{ color: '#ffffff' }}>{item.product.price} MAD</strong>
                        <div className="qty-control">
                          <button className="qty-btn" onClick={() => updateCartQty(item.cartItemId, -1)}>
                            <Minus size={14} />
                          </button>
                          <span style={{ fontSize: '0.85rem', fontWeight: 700, minWidth: 20, textAlign: 'center' }}>
                            {item.quantity}
                          </span>
                          <button className="qty-btn" onClick={() => updateCartQty(item.cartItemId, 1)}>
                            <Plus size={14} />
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>

            {cart.length > 0 && (
              <div className="cart-footer">
                <div className="cart-subtotal-row">
                  <span>Sous-total estimé :</span>
                  <strong>{totalCartPrice} MAD</strong>
                </div>
                <button 
                  className="btn-primary" 
                  style={{ width: '100%', padding: '1rem' }}
                  onClick={() => {
                    window.location.href = 'https://ghostwhite-chamois-737385.hostingersite.com/checkout/';
                  }}
                >
                  COMMANDER MAINTENANT <ArrowRight size={18} />
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Footer */}
      <footer style={{ borderTop: '1px solid var(--border-subtle)', padding: '3.5rem 0', background: '#070709', marginTop: '4rem', fontSize: '0.85rem', color: 'var(--text-muted)' }}>
        <div className="container-max" style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', gap: '2rem' }}>
          <div>
            <div className="brand-logo" style={{ marginBottom: '0.85rem' }}>
              <img src="/logo.jpg" alt="BEST BRAND" className="brand-logo-img" />
              <h2 style={{ fontFamily: 'var(--font-athletic)', fontSize: '1.8rem', color: '#ffffff' }}>BEST BRAND</h2>
            </div>
            <p style={{ maxWidth: 350, lineHeight: 1.6 }}>
              Boutique officielle de streetwear & sportswear haute performance. Articles certifiés authentiques, directement synchronisés avec le système de caisse GestCaisse.
            </p>
          </div>

          <div>
            <h4 style={{ color: '#ffffff', fontWeight: 800, marginBottom: '0.85rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Collections</h4>
            <p style={{ marginBottom: '0.5rem', cursor: 'pointer' }} onClick={() => setSelectedCategory('all')}>Toutes les sorties</p>
            <p style={{ marginBottom: '0.5rem', cursor: 'pointer' }} onClick={() => setSelectedCategory('hoodies')}>Tech Fleece & Vestes</p>
            <p style={{ marginBottom: '0.5rem', cursor: 'pointer' }} onClick={() => setSelectedCategory('sneakers')}>Sneakers</p>
          </div>

          <div>
            <h4 style={{ color: '#ffffff', fontWeight: 800, marginBottom: '0.85rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Infrastructure</h4>
            <p style={{ marginBottom: '0.5rem' }}>• SMART GestCaisse POS Sync</p>
            <p style={{ marginBottom: '0.5rem' }}>• WooCommerce Headless REST API</p>
            <p style={{ marginBottom: '0.5rem' }}>• Hostinger Cloud Infrastructure</p>
          </div>
        </div>
      </footer>
    </div>
  );
}
