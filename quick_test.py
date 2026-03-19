"""
Quick sanity test for the trading system using a small dataset subset.
"""
import pandas as pd
from datetime import timedelta
from pathlib import Path
import sys

# Override config for quick test
class QuickConfig:
    DATA_PATH = "data/btcusdt_15m.csv"
    N_SAMPLES = 2000  # Use only last 2000 samples
    POPULATION_SIZE = 5
    GENERATIONS = 1
    MODEL_TYPES = ["logistic"]  # Only fastest model
    TRAIN_DAYS = 7
    VALID_DAYS = 2
    STEP_DAYS = 2

def main():
    # Import after config override
    from arbos_trading.data.processor import clean_data, create_target
    from arbos_trading.features.horizon import generate_horizon_features
    from arbos_trading.features.technical import add_technical_indicators
    from arbos_trading.features.regime import add_regime_features
    from arbos_trading.models.population import Population
    from arbos_trading.models.base import LogisticModel
    from arbos_trading.ensemble.consensus import ConsensusGate
    from arbos_trading.validation.walk_forward import WalkForwardValidator
    from arbos_trading.trading.simulator import SimulatedTrader
    from arbos_trading.config import TradingConfig, ConsensusConfig

    print("=== QUICK TEST ===")
    print(f"Loading data from {QuickConfig.DATA_PATH}")
    df = pd.read_csv(QuickConfig.DATA_PATH, parse_dates=["open_time"])

    # Take only last N samples
    df = df.sort_values("open_time").tail(QuickConfig.N_SAMPLES).reset_index(drop=True)
    print(f"Using {len(df)} samples (last {QuickConfig.N_SAMPLES})")
    print(f"Date range: {df['open_time'].iloc[0]} to {df['open_time'].iloc[-1]}")

    # Prepare features
    print("Cleaning and adding features...")
    df = clean_data(df)
    df = create_target(df, forward_periods=1)
    horizon_features = generate_horizon_features(df, {"15m": 1})  # only base
    df = df.merge(horizon_features, on="open_time", how="left")
    df = add_technical_indicators(df)
    df = add_regime_features(df)
    df = df.dropna(subset=["target"]).ffill().dropna()
    print(f"Prepared {len(df)} samples with {len(df.columns)} columns")

    feature_names = [col for col in df.columns if col not in [
        "open_time", "open", "high", "low", "close", "volume",
        "quote_volume", "trades_count", "future_close", "target"
    ]]
    print(f"Feature count: {len(feature_names)}")

    # Split
    cutoff = df["open_time"].max() - timedelta(days=QuickConfig.TRAIN_DAYS)
    train_df = df[df["open_time"] <= cutoff].copy()
    test_df = df[df["open_time"] > cutoff].copy()

    if len(train_df) < 100:
        print("ERROR: Not enough training data")
        return

    X_train = train_df[feature_names]
    y_train = train_df["target"]
    X_test = test_df[feature_names] if len(test_df) > 0 else None
    y_test = test_df["target"] if len(test_df) > 0 else None

    print(f"Train size: {len(X_train)}, Test size: {len(X_test) if X_test is not None else 0}")

    # Evolve tiny population
    print("Evolving population...")
    pop = Population(
        population_size=QuickConfig.POPULATION_SIZE,
        model_types=QuickConfig.MODEL_TYPES,
        mutation_rate=0.3,
        crossover_rate=0.4,
        elitism_count=2
    )
    pop.initialize(input_dim=len(feature_names), feature_names=feature_names)

    for gen in range(QuickConfig.GENERATIONS):
        print(f"  Generation {gen+1}/{QuickConfig.GENERATIONS}")
        for ind in pop.individuals:
            try:
                ind.model.fit(X_train, y_train)
                pred = ind.model.predict(X_train, threshold=0.5)
                ind.fitness = (pred == y_train).mean()
            except Exception as e:
                print(f"    Error training {ind.model_type}: {e}")
                ind.fitness = -1000.0
        pop.evolve()
        best = pop.get_best(1)[0]
        print(f"    Best fitness: {best.fitness:.4f}")

    # Get best model
    best_model = pop.get_best(1)[0]
    print(f"Best model: {best_model.model_type} with fitness {best_model.fitness:.4f}")

    # Evaluate on test set if available
    if X_test is not None and len(X_test) > 0:
        try:
            test_pred = best_model.model.predict(X_test, threshold=0.5)
            test_accuracy = (test_pred == y_test).mean()
            print(f"Test accuracy: {test_accuracy:.4f}")
        except Exception as e:
            print(f"Test evaluation error: {e}")

    print("=== TEST COMPLETE ===")
    return {"best_fitness": best_model.fitness, "test_accuracy": test_accuracy if X_test is not None else None}

if __name__ == "__main__":
    result = main()
    print(f"\nFinal result: {result}")
