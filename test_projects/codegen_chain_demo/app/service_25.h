#pragma once
#include <functional>
#include <vector>

class Service25 {
public:
    Service25();
    void execute();
    void registerCallback(std::function<void()> cb);
private:
    std::vector<std::function<void()>> callbacks_;
};
