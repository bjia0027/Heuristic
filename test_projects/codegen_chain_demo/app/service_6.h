#pragma once
#include <functional>
#include <vector>

class Service6 {
public:
    Service6();
    void execute();
    void registerCallback(std::function<void()> cb);
private:
    std::vector<std::function<void()>> callbacks_;
};
