%% correlation_analysis.m
%
% Independent statistical reproduction for the Wearable Health Insights
% Dashboard (MATLAB, Statistics and Machine Learning Toolbox).
%
% Question
%   Is daily active energy burned associated with daily mean heart rate?
%   And how much of that association was an artefact of the sensor's
%   adaptive sampling?
%
% Background
%   The Apple Watch samples heart rate every ~5 s during workouts but only
%   every few minutes at rest, so a plain mean of the samples over-weights
%   exercise. build_daily_summary.py therefore publishes two columns:
%       avg_hr_naive  - plain mean of the samples   (biased upward)
%       avg_hr        - time-weighted mean          (each sample weighted by
%                                                    its hold time)
%   This script runs the same test on both so the size of the bias is
%   visible, and reports Spearman alongside Pearson as a robustness check.
%
% Why MATLAB here
%   Python does all data engineering and rendering; the statistics are
%   re-computed in a second, independent toolchain and the two are checked
%   against each other - the "two methods, one answer" habit of design
%   verification in medical-device work. The Streamlit app displays the
%   figure this script saves.
%
% Author: Nabeel Abdel

clear; clc; close all;

%% 1. Load the daily summary produced by the Python pipeline
T = readtable("daily_summary.csv");

required = ["active_energy_kcal", "avg_hr", "avg_hr_naive", "total_steps"];
missing = required(~ismember(required, string(T.Properties.VariableNames)));
if ~isempty(missing)
    error("daily_summary.csv is missing %s - re-run build_daily_summary.py", strjoin(missing, ", "));
end

% Keep only days with complete pairs (readtable leaves blanks as NaN).
ok      = ~isnan(T.active_energy_kcal) & ~isnan(T.avg_hr) & ~isnan(T.avg_hr_naive);
energy  = T.active_energy_kcal(ok);
hrTW    = T.avg_hr(ok);          % time-weighted (corrected)
hrNaive = T.avg_hr_naive(ok);    % plain sample mean (biased)
n       = numel(energy);
fprintf("Days with complete active-energy / heart-rate pairs: %d\n\n", n);

%% 2. Correlations - corrected vs naive
[rTW, pTW]       = corr(energy, hrTW);                         % Pearson
[rhoTW, prhoTW]  = corr(energy, hrTW,    "Type", "Spearman");  % rank-based
[rNv, pNv]       = corr(energy, hrNaive);
[rhoNv, prhoNv]  = corr(energy, hrNaive, "Type", "Spearman");

fprintf("Active energy vs mean HR\n");
fprintf("  time-weighted : Pearson r = %6.3f (p = %.4g)   Spearman rho = %6.3f (p = %.4g)\n", rTW, pTW, rhoTW, prhoTW);
fprintf("  naive         : Pearson r = %6.3f (p = %.4g)   Spearman rho = %6.3f (p = %.4g)\n", rNv, pNv, rhoNv, prhoNv);
fprintf("  mean sampling bias (naive - weighted): %.1f bpm\n\n", mean(hrNaive - hrTW));

%% 3. Linear regression with 95 % confidence band (corrected metric)
mdl  = fitlm(energy, hrTW);               % hr = b0 + b1 * energy
xFit = linspace(min(energy), max(energy), 100)';
[yFit, yCI] = predict(mdl, xFit, "Alpha", 0.05);   % CI of the mean response

fprintf("OLS fit (time-weighted): HR = %.2f + %.4f * kcal,  R^2 = %.3f\n\n", ...
        mdl.Coefficients.Estimate(1), mdl.Coefficients.Estimate(2), mdl.Rsquared.Ordinary);

%% 4. Figure: naive vs corrected, side by side
blue   = [0.165 0.471 0.839];
orange = [0.922 0.408 0.204];
grey   = [0.63  0.63  0.65 ];

fig = figure("Color", "w", "Position", [100 100 1100 460]);
tl  = tiledlayout(fig, 1, 2, "TileSpacing", "compact", "Padding", "compact");

% --- Left: naive sample mean (the original, biased result) -------------
nexttile;
scatter(energy, hrNaive, 42, grey, "filled", "MarkerFaceAlpha", 0.75); hold on;
cNv = polyfit(energy, hrNaive, 1);
plot(xFit, polyval(cNv, xFit), "-", "Color", orange, "LineWidth", 2); hold off;
grid on; box off;
xlabel("Active energy burned (kcal)"); ylabel("Mean heart rate (bpm)");
title(sprintf("Naive sample mean   r = %.2f, %s", rNv, pLabel(pNv)));
legend(["Daily values", "Linear fit"], "Location", "northwest");

% --- Right: time-weighted mean with 95 % CI ----------------------------
nexttile;
fill([xFit; flipud(xFit)], [yCI(:,1); flipud(yCI(:,2))], orange, ...
     "FaceAlpha", 0.15, "EdgeColor", "none"); hold on;
scatter(energy, hrTW, 42, blue, "filled", "MarkerFaceAlpha", 0.8);
plot(xFit, yFit, "-", "Color", orange, "LineWidth", 2); hold off;
grid on; box off;
xlabel("Active energy burned (kcal)"); ylabel("Mean heart rate (bpm)");
title(sprintf("Time-weighted mean   r = %.2f, %s", rTW, pLabel(pTW)));
legend(["95 % CI of fit", "Daily values", "Linear fit"], "Location", "northwest");

title(tl, "Active energy vs daily mean heart rate - before and after sampling-bias correction");
subtitle(tl, sprintf("n = %d days · MATLAB corr / fitlm · same daily_summary.csv as the dashboard", n), ...
         "Interpreter", "none");

exportgraphics(fig, "energy_vs_hr_correlation.png", "Resolution", 150);
fprintf("Saved energy_vs_hr_correlation.png\n\n");

%% 5. Control comparison: step count vs mean HR
ok2   = ~isnan(T.total_steps) & ~isnan(T.avg_hr);
[rS, pS] = corr(T.total_steps(ok2), T.avg_hr(ok2));
fprintf("Control - steps vs time-weighted HR: r = %.3f, p = %.4g\n", rS, pS);
if pS < 0.05
    fprintf("  -> statistically significant\n");
else
    fprintf("  -> no significant relationship: step volume alone does not track\n");
    fprintf("     heart rate the way exercise intensity does.\n");
end

%% Helper
function s = pLabel(p)
    if p < 0.001
        s = "p < 0.001";
    else
        s = sprintf("p = %.3f", p);
    end
end
