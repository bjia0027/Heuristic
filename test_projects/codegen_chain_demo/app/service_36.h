#pragma once
#include <functional>
#include <vector>

class Service36 {
public:
    Service36();
    void execute();
    void registerCallback(std::function<void()> cb);
private:
    std::vector<std::function<void()>> callbacks_;
};
