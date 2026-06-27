%% correlation_analysis.m
%
% Statistical analysis for the Wearable Health Insights Dashboard.
%
% Question:
%   Across daily summaries of my Apple Watch data, is there a relationship
%   between how much active energy I burn and my average heart rate that
%   day? And does simple step count show the same relationship?
%
% Method:
%   Pearson correlation + ordinary least-squares linear regression
%   (Statistics and Machine Learning Toolbox). The active-energy vs
%   heart-rate figure is saved to energy_vs_hr_correlation.png, which the
%   Streamlit dashboard (app.py) then displays.
%
% Why MATLAB here:
%   Python handles all of the data engineering and dashboard rendering;
%   MATLAB is used deliberately for the statistics step, mirroring the
%   cross-toolchain workflow common in biomedical signal-processing work.
%
% Author: Nabeel Abdel

clear; clc; close all;

%% 1. Load the daily summary produced by the Python pipeline
% build_daily_summary.py writes daily_summary.csv (one row per day), which
% is committed to the repo, so this script reproduces the published figure.
T = readtable("daily_summary.csv");

% Keep only days that have BOTH variables, so the statistics are computed
% on complete pairs (readtable leaves missing cells as NaN).
validEnergyHR = ~isnan(T.active_energy_kcal) & ~isnan(T.avg_hr);
energy = T.active_energy_kcal(validEnergyHR);
hr     = T.avg_hr(validEnergyHR);

fprintf("Days with both active energy and avg HR: %d\n", numel(energy));

%% 2. Active energy vs average heart rate
% corr returns the Pearson correlation coefficient R and its p-value.
[R, p] = corr(energy, hr);
R2 = R^2;

% Fit a simple linear regression line (hr = b0 + b1*energy) for the plot.
coeffs = polyfit(energy, hr, 1);
xFit = linspace(min(energy), max(energy), 100);
yFit = polyval(coeffs, xFit);

fprintf("\nActive energy vs avg HR:\n");
fprintf("  R   = %.3f\n", R);
fprintf("  R^2 = %.3f\n", R2);
fprintf("  p   = %.4g\n", p);

%% 3. Plot and save the figure the dashboard displays
if p < 0.001
    pStr = "p < 0.001";
else
    pStr = sprintf("p = %.3f", p);
end

fig = figure("Color", "w", "Position", [100 100 760 520]);
scatter(energy, hr, 45, [0 0.443 0.890], "filled", "MarkerFaceAlpha", 0.7);
hold on;
plot(xFit, yFit, "-", "Color", [0.910 0.314 0.227], "LineWidth", 2);
hold off;

grid on;
xlabel("Active Energy Burned (kcal)", "FontSize", 12);
ylabel("Average Heart Rate (bpm)", "FontSize", 12);
title(sprintf("Active Energy vs Average Heart Rate  (R = %.3f, %s)", R, pStr), ...
      "FontSize", 13);
legend(["Daily values", "Linear fit"], "Location", "northwest");

% Save under the filename app.py looks for.
exportgraphics(fig, "energy_vs_hr_correlation.png", "Resolution", 150);
fprintf("\nSaved energy_vs_hr_correlation.png\n");

%% 4. Control comparison: step count vs average heart rate
% Steps measure movement *volume*; active energy captures movement
% *intensity*. If the two behave differently against heart rate, that is a
% meaningful physiological finding, not a failed test.
validStepsHR = ~isnan(T.total_steps) & ~isnan(T.avg_hr);
steps = T.total_steps(validStepsHR);
hr2   = T.avg_hr(validStepsHR);

[Rs, ps] = corr(steps, hr2);
fprintf("\nStep count vs avg HR (control):\n");
fprintf("  R = %.3f, p = %.4g\n", Rs, ps);

if ps < 0.05
    fprintf("  -> statistically significant\n");
else
    fprintf("  -> NO significant relationship. A valid result: step volume\n");
    fprintf("     alone does not track heart rate the way energy intensity does.\n");
end
